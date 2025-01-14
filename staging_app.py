import streamlit as st
from snowflake.snowpark import Session
from snowflake.core import Root
from snowflake.ml.utils import connection_params
import pandas as pd
import json
from PIL import Image
from openai import OpenAI
import logging
import time
import base64

class SnowflakeConnection:
    def __init__(self):
        self.connection_parameters = {
            "account": st.secrets["account"],
            "user": st.secrets["user"],
            "password": st.secrets["password"],
            "database": st.secrets["database"],
            "warehouse": st.secrets["warehouse"],
            "schema": st.secrets["schema"]
        }
        self.session = self._get_snowflake_session()
        self.root = Root(self.session)
        
    @st.cache_resource
    def _get_snowflake_session(_self):
        return Session.builder.configs(_self.connection_parameters).create()

class SearchService:
    def __init__(self, snowflake_conn):
        self.NUM_CHUNKS = 10
        self.COLUMNS = [
            "chunk",
            "relative_path",
            "PRODUCTNAME",
            "COMPANYNAME",
            "CATEGORY_EPA_TYPE",
            "SIGNAL_WORD"
        ]
        self.snowflake_conn = snowflake_conn
        self.service = self._initialize_service()
    
    def _initialize_service(self):
        database = st.secrets["database"]
        schema = st.secrets["schema"]
        service_name = f"CC_SEARCH_SERVICE_CS_{self.snowflake_conn.connection_parameters['database']}"
        return self.snowflake_conn.root.databases[database].schemas[schema].cortex_search_services[service_name]
    
    def search(self, query, category="ALL"):
        if category == "ALL":
            response = self.service.search(query, self.COLUMNS, limit=self.NUM_CHUNKS)
        else:
            filter_obj = {"@eq": {"PRODUCTNAME": category}}
            response = self.service.search(query, self.COLUMNS, filter=filter_obj, limit=self.NUM_CHUNKS)
        return response.json()

class LocationService:
    def __init__(self, snowflake_conn):
        self.session = snowflake_conn.session
    
    def search_locations(self, search_term=''):
        base_query = "SELECT LOCATION FROM DEV_DP_APP.MODELED.US_ADDRESS_LIST"
        if not search_term:
            load_sql = f"{base_query} LIMIT 20"
        else:
            load_sql = f"{base_query} WHERE CONTAINS(LOWER(LOCATION), LOWER('{search_term}')) LIMIT 20"
        
        try:
            result = self.session.sql(load_sql).to_pandas()
            return result['LOCATION'].to_list()
        except Exception as e:
            st.error(f"Error fetching locations: {str(e)}")
            return [""]

class ImageAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    def analyze(self, image_bytes, prompt):
        try:
            base64_image = self._encode_image_to_base64(image_bytes)
            response = self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error analyzing image: {str(e)}"
    
    def _encode_image_to_base64(self, image_bytes):
        return base64.b64encode(image_bytes).decode('utf-8')

class ChatManager:
    def __init__(self, search_service):
        self.search_service = search_service
        self.slide_window = 7
        
    def get_chat_history(self):
        if "messages" not in st.session_state:
            return []
        start_index = max(0, len(st.session_state.messages) - self.slide_window)
        return st.session_state.messages[start_index:-1]
    
    def summarize_question(self, chat_history, question):
        prompt = f"""
            Based on the chat history below and the question, generate a query that extend the question
            with the chat history provided. The query should be in natural language. 
            Answer with only the query. Do not add any explanation.
            
            <chat_history>
            {chat_history}
            </chat_history>
            <question>
            {question}
            </question>
            """
        from snowflake.cortex import Complete
        summary = Complete(st.session_state.model_name, prompt)
        return summary.replace("'", "")
    
    def create_prompt(self, question):
        image_analysis = st.session_state.get('image_analysis')
        chat_history = self.get_chat_history()
        
        if chat_history:
            question_summary = self.summarize_question(chat_history, question)
            prompt_context = self.search_service.search(question_summary, st.session_state.category_value)
        else:
            prompt_context = self.search_service.search(question, st.session_state.category_value)
            
        prompt = f"""
            You are an agronomist who can advise on pesticides. 
            
            When the question is general about a product, you advice on topics such as pesticide's labeling and usage. 
            You can speak about the active ingredient, dosage, relevant crop/plant, PPE needed, Environment hazards, 
            mode of action, target pest.
            
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
            {question}
            </question>
            Answer:
            """
        
        json_data = json.loads(prompt_context)
        relative_paths = set(item['relative_path'] for item in json_data['results'])
        
        return prompt, relative_paths

class KroniaApp:
    def __init__(self):
        self.snowflake_conn = SnowflakeConnection()
        self.search_service = SearchService(self.snowflake_conn)
        self.location_service = LocationService(self.snowflake_conn)
        self.image_analyzer = ImageAnalyzer()
        self.chat_manager = ChatManager(self.search_service)
        
    def setup_page(self):
        st.set_page_config(page_title="Kronia", layout="wide")
        self._create_structure()
        st.session_state.model_name = 'mistral-large2'
        
    def run(self):
        self.setup_page()
        self._show_settings()
        self._config_options()
        self._init_messages()
        self._display_chat_history()
        self._handle_user_input()
    
    def _show_settings(self):
        # Implementation of settings UI
        pass
        
    def _config_options(self):
        # Implementation of configuration options
        pass
        
    def _init_messages(self):
        if "start_over" not in st.session_state:
            st.session_state.start_over = False
        if st.session_state.start_over or "messages" not in st.session_state:
            st.session_state.messages = []
            
    def _display_chat_history(self):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
    def _handle_user_input(self):
        if question := st.chat_input("What do you want to know about your products?"):
            st.session_state.messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
                
            with st.chat_message("assistant"):
                self._process_question(question)
    
    def _process_question(self, question):
        message_placeholder = st.empty()
        question = question.replace("'", "")
        
        with st.spinner(f"{st.session_state.model_name} thinking..."):
            from snowflake.cortex import Complete
            prompt, relative_paths = self.chat_manager.create_prompt(question)
            response = Complete(st.session_state.model_name, prompt)
            response = response.replace("'", "")
            
            message_placeholder.markdown(response)
            self._display_related_documents(relative_paths)
            
            st.session_state.messages.append({"role": "assistant", "content": response})
    
    def _display_related_documents(self, relative_paths):
        if relative_paths != "None":
            st.markdown("Related Documents")
            for path in relative_paths:
                cmd = f"select GET_PRESIGNED_URL(@DEV_SRC_INGEST.EPA_RAW.PDF_STORE, '{path}', 360) as URL_LINK from directory(@DEV_SRC_INGEST.EPA_RAW.PDF_STORE)"
                df_url_link = self.snowflake_conn.session.sql(cmd).to_pandas()
                url_link = df_url_link._get_value(0, 'URL_LINK')
                st.markdown(f"Doc: [{path}]({url_link})")
    
    def _create_structure(self):
        # Implementation of UI structure using st.markdown()
        pass

if __name__ == "__main__":
    app = KroniaApp()
    app.run()