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

pd.set_option("max_colwidth",None)

# Create Snowflake session
connection_parameters = {
   "account": st.secrets["account"],
   "user": st.secrets["user"],
   "password": st.secrets["password"],
   "database": "AJJAY_SANDBOX", 
   "warehouse": "compute_wh",
   "schema": "PUBLIC"            
}

# create from a Snowflake Connection
#connection = connect(**connection_parameters)
#root = Root(connection)
# or create from a Snowpark Session
@st.cache_resource
def get_snowflake_session():
    return (
        Session.builder
        .config("account", st.secrets["account"])
        .config("user", st.secrets["user"])
        .config("password", st.secrets["password"])
        .config("database", "AJJAY_SANDBOX")
        .config("warehouse", "compute_wh")
        .config("schema", "PUBLIC")
        .create()
    )

# Get the session only once and reuse it
session = get_snowflake_session()
root = Root(session)



### Default Values
NUM_CHUNKS = 10 # Num-chunks provided as context. Play with this to check how it affects your accuracy
slide_window = 7 # how many last conversations to remember. This is the slide window.

# service parameters
CORTEX_SEARCH_DATABASE = "AJJAY_SANDBOX"
CORTEX_SEARCH_SCHEMA = "PUBLIC"
CORTEX_SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"
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
   
### Functions
     
def config_options():

    st.sidebar.title("Select Options")

    categories = session.table('ALL_CATEGORICAL_DOCS_CHUNK_TABLE').select('PRODUCTNAME').distinct().collect()

    cat_list = ['ALL']
    for cat in categories:
        cat_list.append(cat.PRODUCTNAME)
            
    st.sidebar.selectbox('Select what products you are looking for', cat_list, key = "category_value")

    uploaded_file = st.sidebar.file_uploader("Upload an image with crop pest damage...", type=["jpg", "jpeg", "png"], key="uploaded_file")
    image_workflow()
    st.sidebar.button("Start Over", on_click=init_messages)
    st.sidebar.expander("Session State").write(st.session_state)

def init_messages():
    
   # Initialize chat history
    if "messages" not in st.session_state:
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
    else:
        st.session_state.image_analysis = None

def main():
    
    st.title(f":speech_balloon: Chat with Pesticide Products Label Documents 🌾")
    st.session_state.model_name = 'mistral-large2'
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