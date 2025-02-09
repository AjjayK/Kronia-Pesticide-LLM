import streamlit as st
import pandas as pd

@st.cache_data
def get_dropdown_data(_session, app_db):
    query = f"""
    SELECT *
    FROM {app_db}.APP_ASSETS.DROPDOWN_DATA 
    """

    data_df = _session.sql(query).to_pandas()
    return data_df

def add_all_option(series):
    return pd.concat([pd.Series(['ALL']), series.drop_duplicates()]).reset_index(drop=True)

def get_product_list(session, app_db):

    data_df = get_dropdown_data(session, app_db)

    site_options = pd.Series(sorted(data_df['SITE'].unique()))
    selected_site = st.sidebar.selectbox('Select your crop and treatment', add_all_option(site_options), index=0)
    if selected_site == 'ALL':
        filtered_data_by_site = data_df
    else:
        filtered_data_by_site = data_df[data_df['SITE'] == selected_site]


    pest_options = pd.Series(sorted(filtered_data_by_site['PEST'].unique()))
    selected_pest = st.sidebar.selectbox('Select the pest on your crop/site', add_all_option(pest_options), index=0)
    if selected_pest == 'ALL':
        filtered_data_by_pest = filtered_data_by_site
    else:
        filtered_data_by_pest = filtered_data_by_site[data_df['PEST'] == selected_pest]


    product_options = pd.Series(sorted(filtered_data_by_pest['PRODUCTNAME'].unique()))
    selected_product = st.sidebar.selectbox('Select a product of interest', add_all_option(product_options), index=0)
    if selected_product == 'ALL':
        filtered_data_by_product = filtered_data_by_pest
    else:
        filtered_data_by_product = filtered_data_by_pest[filtered_data_by_pest['PRODUCTNAME'] == selected_product]

    # Display the selected data
    if selected_pest == 'ALL' and selected_site == 'ALL' and selected_product == 'ALL':
        return "ALL"
    else:
        return filtered_data_by_product
