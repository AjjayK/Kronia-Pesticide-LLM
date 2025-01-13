import streamlit as st # Import python packages
from snowflake.snowpark import Session
from snowflake.ml.utils import connection_params
from snowflake.connector import connect
from snowflake.core import Root

from snowflake.cortex import Complete
from snowflake.core import Root

import pandas as pd
import json
from PIL import Image
import io
import base64
from openai import OpenAI
import logging
import time
from datetime import datetime
pd.set_option("max_colwidth",None)
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

#experimental
from streamlit_extras.stylable_container import stylable_container

# Create Snowflake session
connection_parameters = {
   "account": st.secrets["account"],
   "user": st.secrets["user"],
   "password": st.secrets["password"],
   "database": st.secrets["database"], 
   "warehouse": st.secrets["warehouse"],
   "schema": st.secrets["schema"]           
}

# create from a Snowflake Connection
#connection = connect(**connection_parameters)
#root = Root(connection)
# or create from a Snowpark Session
@st.cache_resource
def get_snowflake_session():
    return (
        Session.builder
        .configs(connection_parameters)
        .create()
    )

# Get the session only once and reuse it
session = get_snowflake_session()
root = Root(session)



### Default Values
NUM_CHUNKS = 10 # Num-chunks provided as context. Play with this to check how it affects your accuracy
slide_window = 7 # how many last conversations to remember. This is the slide window.

# service parameters
CORTEX_SEARCH_DATABASE = st.secrets["database"]
CORTEX_SEARCH_SCHEMA = st.secrets["schema"]
CORTEX_SEARCH_SERVICE = f"CC_SEARCH_SERVICE_CS_{connection_parameters['database']}"
######
######

# columns to query in the service
COLUMNS = [
    "chunk",
    "relative_path",
    "PRODUCTNAME",
    "COMPANYNAME",
    "CATEGORY_EPA_TYPE",
    "SIGNAL_WORD"
]

                      

svc = root.databases[CORTEX_SEARCH_DATABASE].schemas[CORTEX_SEARCH_SCHEMA].cortex_search_services[CORTEX_SEARCH_SERVICE]

def search_locations(search_term = ''):
    if not search_term:
        # If no search term, return limited initial results
        load_sql = """
        SELECT LOCATION 
        FROM DEV_DP_APP.MODELED.US_ADDRESS_LIST 
        LIMIT 20
        """
    else:
        # If there's a search term, filter locations that match
        load_sql = f"""
        SELECT LOCATION 
        FROM DEV_DP_APP.MODELED.US_ADDRESS_LIST 
        WHERE CONTAINS(LOWER(LOCATION), LOWER('{search_term}'))
        LIMIT 20
        """
    
    try:
        result = session.sql(load_sql).to_pandas()
        return result['LOCATION'].to_list()  # Add empty option at start
    except Exception as e:
        st.error(f"Error fetching locations: {str(e)}")
        return [""]
   
### Functions
def show_settings():
    # Initialize session states
    if 'show_settings' not in st.session_state:
        st.session_state.show_settings = False
    if 'user_location' not in st.session_state:
        user_id = st.session_state.get('user_id', 'default_user') 
        load_sql = f"""
        SELECT LOCATION 
        FROM AJJAY_SANDBOX.APP_ASSETS.USER_SETTINGS 
        WHERE USER_ID = '{user_id}'
        """
        result = session.sql(load_sql).collect()
        if len(result) > 0:
            st.session_state.user_location = result[0]['LOCATION']
        else:
            st.session_state.user_location = ""

    if 'save_time' not in st.session_state:
        st.session_state.save_time = None

    # Toggle function for the settings visibility
    def toggle_settings():
        st.session_state.show_settings = not st.session_state.show_settings

    # Create settings button in the sidebar
    st.sidebar.button("⚙️ Settings", on_click=toggle_settings)

    # Auto-hide logic
    if st.session_state.save_time:
        if time.time() - st.session_state.save_time > 2:  # 2 seconds passed
            st.session_state.show_settings = False
            st.session_state.save_time = None

    # Show settings when enabled
    if st.session_state.show_settings:
        with st.sidebar.expander("Settings", expanded=True):
            # Location input
            query = st.text_input("Type location to filter dropdown")
            locations = search_locations(query)
            new_location = st.selectbox(
                "Choose your Location",
                options = locations,
                key="location_input",
                placeholder="Select location from dropdown...",
            )
            
            # Save button
            if st.button("Save Settings"):
                st.session_state.user_location = new_location
                st.session_state.save_time = time.time()  # Record save time


                # Save to Snowflake
                user_id = st.session_state.get('user_id', 'default_user')
                try:
                    upsert_sql = f"""
                    MERGE INTO AJJAY_SANDBOX.APP_ASSETS.USER_SETTINGS AS target
                    USING (SELECT '{user_id}' AS USER_ID, '{new_location}' AS LOCATION) AS source
                    ON target.USER_ID = source.USER_ID
                    WHEN MATCHED THEN
                        UPDATE SET LOCATION = source.LOCATION, LAST_UPDATED = CURRENT_TIMESTAMP()
                    WHEN NOT MATCHED THEN
                        INSERT (USER_ID, LOCATION) VALUES (source.USER_ID, source.LOCATION)
                    """
                    session.sql(upsert_sql).collect()
                    st.success("Settings saved!") 
                except Exception as e:
                    st.error(f"Error saving settings: {e}")    

def image_workflow():
    if st.session_state.uploaded_file is not None and st.session_state.image_analysis is None:
        # Display the uploaded image
        image = Image.open(st.session_state.uploaded_file)
        st.sidebar.image(image, caption="Uploaded Image", use_column_width=True)
        with st.spinner("Analyzing image..."):
            # Get image bytes
            img_bytes = st.session_state.uploaded_file.getvalue()
            
            # Get analysis
            image_prompt = "You are an expert agronomist. Look into the picture and identify what the issue with the plant/crop is."
            analysis = analyze_image(img_bytes, image_prompt)
            
            # Store results
            st.session_state.image_analysis = analysis
    if st.session_state.uploaded_file is None:
        st.session_state.image_analysis = None
     
def config_options():

    st.sidebar.title("Select Options")

    categories = session.table('DOCS_CHUNKS_TABLE').select('PRODUCTNAME').distinct().collect()

    cat_list = ['ALL']
    for cat in categories:
        cat_list.append(cat.PRODUCTNAME)
            
    st.sidebar.selectbox('Select what products you are looking for', cat_list, key = "category_value")

    uploaded_file = st.sidebar.file_uploader("Upload an image with crop pest damage...", type=["jpg", "jpeg", "png"], key="uploaded_file")
    image_workflow()
    st.sidebar.button("Start Over", on_click=init_messages, key="start_over")
    st.sidebar.expander("Session State").write(st.session_state)

def init_messages():
    
   # Initialize chat history
    if st.session_state.start_over or "messages" not in st.session_state:
        st.session_state.messages = []

def get_similar_chunks_search_service(query):

    #response = svc.search(query, COLUMNS, limit=NUM_CHUNKS)

    if st.session_state.category_value == "ALL":
        response = svc.search(query, COLUMNS, limit=NUM_CHUNKS)
    else: 
        st.write(st.session_state.category_value)
        filter_obj = {"@eq": {"PRODUCTNAME": st.session_state.category_value} }
        response = svc.search(query, COLUMNS, filter=filter_obj, limit=NUM_CHUNKS)

    st.sidebar.json(response.json())
    
    return response.json()  

def get_chat_history():
#Get the history from the st.session_stage.messages according to the slide window parameter
    
    chat_history = []
    
    start_index = max(0, len(st.session_state.messages) - slide_window)
    for i in range (start_index , len(st.session_state.messages) -1):
         chat_history.append(st.session_state.messages[i])

    return chat_history

def summarize_question_with_history(chat_history, question):
# To get the right context, use the LLM to first summarize the previous conversation
# This will be used to get embeddings and find similar chunks in the docs for context

    prompt = f"""
        Based on the chat history below and the question, generate a query that extend the question
        with the chat history provided. The query should be in natual language. 
        Answer with only the query. Do not add any explanation.
        
        <chat_history>
        {chat_history}
        </chat_history>
        <question>
        {question}
        </question>
        """
    
    sumary = Complete(st.session_state.model_name, prompt)   

    st.sidebar.text("Summary to be used to find similar chunks in the docs:")
    st.sidebar.caption(sumary)

    sumary = sumary.replace("'", "")

    return sumary

def create_prompt (myquestion):
    image_analysis = st.session_state.image_analysis
    chat_history = get_chat_history()

    if chat_history != []: #There is chat_history, so not first question
        question_summary = summarize_question_with_history(chat_history, myquestion)
        prompt_context =  get_similar_chunks_search_service(question_summary)
    else:
        prompt_context = get_similar_chunks_search_service(myquestion) #First question when using history
  
    prompt = f"""
           You are an agronomist who can advise on pesticides. 
           
           When the question is general about a product, you advice on topics such as pesticide's labeling and usage. You can speak about the active ingredient, 
           dosage, relevant crop/plant, PPE needed, Environment hazards, mode of action, target pest
            
           You can utilize the information contained from the CONTEXT provided
           between <context> and </context> tags.
           
           You can utilize the information contained from the IMAGE ANALYSIS provided
           between <image_analysis> and </image_analysis> tags.

           You offer a chat experience considering the information included in the CHAT HISTORY
           provided between <chat_history> and </chat_history> tags..
           When answering the question contained between <question> and </question> tags
           be a bit detailed and please DO NOT HALLUCINATE. 
           If you don´t have the information just say so.
           
           Do not mention the CONTEXT used in your answer.
           Do not mention the CHAT HISTORY used in your answer.
           Do not repeat the CHAT HISTORY again in your answer.
           Only answer the question if you can extract it from the CONTEXT provided.
           
           <chat_history>
           {chat_history}
           </chat_history>
           <context>          
           {prompt_context}
           </context>
           <image_analysis>
           {image_analysis}
           </image_analysis>
           <question>  
           {myquestion}
           </question>
           Answer: 
           """
    
    json_data = json.loads(prompt_context)

    relative_paths = set(item['relative_path'] for item in json_data['results'])

    return prompt, relative_paths


def answer_question(myquestion):

    prompt, relative_paths =create_prompt (myquestion)

    response = Complete(st.session_state.model_name, prompt)   

    return response, relative_paths

def get_openai_client():
    api_key = st.secrets["OPENAI_API_KEY"]  # Store your API key in Streamlit secrets
    return OpenAI(api_key=api_key)

def encode_image_to_base64(image_bytes):
    """Convert image bytes to base64 string"""
    return base64.b64encode(image_bytes).decode('utf-8')

def analyze_image(image_bytes, prompt):
    """Analyze image using GPT-4V"""
    client = get_openai_client()
    
    # Convert image to base64
    base64_image = encode_image_to_base64(image_bytes)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing image: {str(e)}"
    
def create_structure():
    st.markdown(
        """
        <style>
        .footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            padding: 8px;
            text-align: center;
            color: rgba(60, 60, 67, 0.7);
            z-index: 999;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            letter-spacing: 0.2px;
            backdrop-filter: blur(20px);  /* Increased blur for more frosted look */
            -webkit-backdrop-filter: blur(20px);
            border-top: 1px solid rgba(255, 255, 255, 0.3);  /* Lighter border for glass effect */
            box-shadow: 0 -10px 15px rgba(255, 255, 255, 0.4);  /* Subtle glow */
        }

        @supports not (backdrop-filter: blur(20px)) {
            .footer {
                background: rgba(250, 250, 250, 0.95);  /* Fallback for browsers that don't support backdrop-filter */
            }
        }

        .title-container {
            text-align: left;
            padding: 0;  /* Removed padding to move up */
            margin: -3rem 0 2rem 1rem;  /* Negative top margin to move up, left margin for alignment */
        }

        .main {
            margin-bottom: 45px;
        }
        
        .main-title {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 2.5rem;
            font-weight: 700;
            color: #1E3C72;
            margin-bottom: 0.1rem;
            letter-spacing: -0.5px;
        }
        
        .subtitle {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 1.2rem;  /* Reduced from 1.5rem */
            font-weight: 400;
            color: #4A4A4A;
            margin-top: 0;
            letter-spacing: -0.2px;
            line-height: 1.4;  /* Added for better readability */
        }

        .footer {
            animation: fadeInUp 0.3s ease-out;
        }
        </style>

        
        <div class="title-container">
            <h1 class="main-title">🌾 Kronia</h1>
            <h4 class="subtitle">💬 Chat with Pesticide Products Label Documents</h4>
        </div>

        <div class="footer">
            <div class="footer-content">
                <span>Kronia can make mistakes. Please double check.</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
def main():

    create_structure()
    st.session_state.model_name = 'mistral-large2'
    show_settings()
    config_options()
    init_messages()
    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Accept user input
    if question := st.chat_input("What do you want to know about your products?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": question})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(question)
        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
    
            question = question.replace("'","")
    
            with st.spinner(f"{st.session_state.model_name} thinking..."):
                response, relative_paths = answer_question(question)            
                response = response.replace("'", "")
                message_placeholder.markdown(response)

                if relative_paths != "None":
                    st.markdown("Related Documents")
                    for path in relative_paths:
                        cmd2 = f"select GET_PRESIGNED_URL(@DEV_SRC_INGEST.EPA_RAW.PDF_STORE, '{path}', 360) as URL_LINK from directory(@DEV_SRC_INGEST.EPA_RAW.PDF_STORE)"
                        df_url_link = session.sql(cmd2).to_pandas()
                        url_link = df_url_link._get_value(0,'URL_LINK')
            
                        display_url = f"Doc: [{path}]({url_link})"
                        st.markdown(display_url)
                
        
        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()