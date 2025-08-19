from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import snowflake.connector
import streamlit as st
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

HOST = "gmcpdcz-mt01740.snowflakecomputing.com"
DATABASE = "DEV_SRC_INGEST"
SCHEMA = "EPA_RAW"
STAGE = "CORTEX_ANALYST"
FILE = "epa_analyst.yaml"

p_key_str = st.secrets["private_key_file"]
p_key_bytes = p_key_str.encode('utf-8')
p_key = serialization.load_pem_private_key(
            p_key_bytes,
            password=None, 
            backend=default_backend()
        )

if 'CONN' not in st.session_state or st.session_state.CONN is None:
    st.session_state.CONN = snowflake.connector.connect(
        user=st.secrets["user"],
        password=st.secrets["password"],
        account=st.secrets["account"],
        host=HOST,
        port=443,
        warehouse="COMPUTE_WH",
        role="ACCOUNTADMIN",
        #private_key=p_key,

    )

st.set_page_config(page_title="Kronia Analyst", page_icon="🌾", layout="wide", initial_sidebar_state="auto", menu_items=None)

@st.cache_data
def get_semantic_model_content() -> Dict[str, Any]:
    """Fetches and parses the semantic model YAML file from Snowflake stage."""
    try:
        cursor = st.session_state.CONN.cursor()
        cursor.execute(f"SELECT $1 FROM @{DATABASE}.{SCHEMA}.{STAGE}/{FILE}")
        result = cursor.fetchall()
        cursor.close()
        
        if result:
            # Concatenate all rows if multiple
            if len(result) > 1:
                yaml_content = '\n'.join([str(row[0]) for row in result])
            else:
                yaml_content = result[0][0]
            
            return yaml.safe_load(yaml_content)
        return {}
    except Exception as e:
        st.error(f"Failed to fetch semantic model: {str(e)}")
        return {}


def send_message(prompt: str) -> Dict[str, Any]:
    """Calls the REST API and returns the response."""
    request_body = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "semantic_model_file": f"@{DATABASE}.{SCHEMA}.{STAGE}/{FILE}",
    }
    resp = requests.post(
        url=f"https://{HOST}/api/v2/cortex/analyst/message",
        json=request_body,
        headers={
            "Authorization": f'Snowflake Token="{st.session_state.CONN.rest.token}"',
            "Content-Type": "application/json",
        },
    )
    request_id = resp.headers.get("X-Snowflake-Request-Id")
    if resp.status_code < 400:
        return {**resp.json(), "request_id": request_id}  # type: ignore[arg-type]
    else:
        raise Exception(
            f"Failed request (id: {request_id}) with status {resp.status_code}: {resp.text}"
        )


def process_message(prompt: str) -> None:
    """Processes a message and adds the response to the chat."""
    st.session_state.messages.append(
        {"role": "user", "content": [{"type": "text", "text": prompt}]}
    )
    
    with st.spinner("Generating response..."):
        response = send_message(prompt=prompt)
        request_id = response["request_id"]
        content = response["message"]["content"]
    
    st.session_state.messages.append(
        {"role": "assistant", "content": content, "request_id": request_id}
    )


def display_content(
    content: List[Dict[str, str]],
    request_id: Optional[str] = None,
    message_index: Optional[int] = None,
) -> None:
    """Displays a content item for a message."""
    message_index = message_index or len(st.session_state.messages)
    if request_id:
        with st.expander("Request ID", expanded=False):
            st.markdown(request_id)
    for item in content:
        if item["type"] == "text":
            st.markdown(item["text"])
        elif item["type"] == "suggestions":
            with st.expander("Suggestions", expanded=True):
                for suggestion_index, suggestion in enumerate(item["suggestions"]):
                    if st.button(suggestion, key=f"{message_index}_{suggestion_index}"):
                        st.session_state.active_suggestion = suggestion
        elif item["type"] == "sql":
            with st.expander("SQL Query", expanded=False):
                st.code(item["statement"], language="sql")
            with st.expander("Results", expanded=True):
                with st.spinner("Running SQL..."):
                    df = pd.read_sql(item["statement"], st.session_state.CONN)
                    if len(df.index) > 1:
                        data_tab, line_tab, bar_tab = st.tabs(
                            ["Data", "Line Chart", "Bar Chart"]
                        )
                        data_tab.dataframe(df)
                        if len(df.columns) > 1:
                            df = df.set_index(df.columns[0])
                        with line_tab:
                            st.line_chart(df)
                        with bar_tab:
                            st.bar_chart(df)
                    else:
                        st.dataframe(df)


def display_table_info_sidebar():
    """Displays table information in the left sidebar."""
    semantic_model = get_semantic_model_content()
    if not semantic_model:
        st.warning("Could not load semantic model information.")
        return
    
    st.header("📋 Tables")
    
    # Display tables information
    if "tables" in semantic_model and semantic_model["tables"]:
        for table in semantic_model["tables"]:
            table_name = table.get("name", "Unknown")
            base_table = table.get("base_table", {})
            
            with st.expander(f"Table: {table_name}", expanded=False):
                # Display base table info
                if base_table:
                    st.markdown(f"**Database:** {base_table.get('database', '')}")
                    st.markdown(f"**Schema:** {base_table.get('schema', '')}")
                    st.markdown(f"**Table:** {base_table.get('table', '')}")
                
                # Display dimensions (columns)
                if "dimensions" in table and table["dimensions"]:
                    st.markdown("**Dimensions:**")
                    dim_data = []
                    for dim in table["dimensions"]:
                        dim_info = {
                            "Column": dim.get("name", ""),
                            "Description": dim.get("description", ""),
                            "Sample Values": ", ".join(dim.get("sample_values", [])[:3]) if dim.get("sample_values") else ""
                        }
                        dim_data.append(dim_info)
                    
                    if dim_data:
                        st.dataframe(pd.DataFrame(dim_data), use_container_width=True, hide_index=True)
                
                # Display facts (if any)
                if "facts" in table and table["facts"]:
                    st.markdown("**Facts (Measures):**")
                    fact_data = []
                    for fact in table["facts"]:
                        fact_info = {
                            "Column": fact.get("name", ""),
                            "Description": fact.get("description", ""),
                            "Sample Values": ", ".join(map(str, fact.get("sample_values", [])[:3])) if fact.get("sample_values") else ""
                        }
                        fact_data.append(fact_info)
                    
                    if fact_data:
                        st.dataframe(pd.DataFrame(fact_data), use_container_width=True, hide_index=True)


def display_sample_queries_sidebar():
    """Displays sample queries in the right sidebar."""
    semantic_model = get_semantic_model_content()
    if not semantic_model:
        return
    
    # Add some styling to the sidebar
    st.markdown("""
    <style>
    .sample-queries {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.header("💡 Sample Queries")
    
        # Display verified queries
    if "verified_queries" in semantic_model and semantic_model["verified_queries"]:
        with st.container():
            st.markdown('<div class="sample-queries">', unsafe_allow_html=True)
            for i, query in enumerate(semantic_model["verified_queries"], 1):
                query_name = query.get("name", f"Query {i}")
                
                # Create a more compact and visually appealing query card
                st.markdown(f"**{query_name}**")
                
                if "question" in query:
                    st.markdown(f"*{query['question']}*")
                    if st.button(f"Ask this question", key=f"query_btn_{i}", use_container_width=True):
                        st.session_state.active_suggestion = query['question']
                        st.rerun()
                
                # Show SQL in a collapsible section if available
                if "sql" in query:
                    with st.expander("View SQL", expanded=False):
                        st.code(query["sql"], language="sql")
                
                # Show verification info if available
                if "verified_by" in query:
                    st.caption(f"✓ Verified by: {query['verified_by']}")
                
                # Add separator between queries
                if i < len(semantic_model["verified_queries"]):
                    st.divider()
            st.markdown('</div>', unsafe_allow_html=True)


st.title("Cortex Analyst")


# Setup sidebars
with st.sidebar:
    display_table_info_sidebar()

# Main content and right sidebar using columns
col1, col2 = st.columns([2.5, 1])

with col1:
    # Main chat interface
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.suggestions = []
        st.session_state.active_suggestion = None

    # Chat messages container with fixed height
    chat_container = st.container(height=600)
    
    with chat_container:
        # Display existing messages
        for message_index, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                display_content(
                    content=message["content"],
                    request_id=message.get("request_id"),
                    message_index=message_index,
                )

    # Chat input stays below the container
    user_input = st.chat_input("What is your question?")
    
    if user_input:
        process_message(prompt=user_input)
        st.rerun()

    # Handle active suggestions
    if st.session_state.active_suggestion:
        process_message(prompt=st.session_state.active_suggestion)
        st.session_state.active_suggestion = None
        st.rerun()

# Right sidebar
with col2:
    display_sample_queries_sidebar()