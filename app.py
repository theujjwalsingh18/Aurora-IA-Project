import os
import time
import csv
import yaml
import json
from PIL import Image
import pandas as pd
import numpy as np
import streamlit as st
import streamlit_lottie as st_lottie
import matplotlib.pyplot as plt
import seaborn as sns
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities import LoginError
from streamlit_authenticator.utilities.hasher import Hasher
from streamlit_gsheets import GSheetsConnection
from ydata_profiling import ProfileReport
import google.generativeai as genai
from dotenv import load_dotenv
from sklearn.impute import SimpleImputer

# Streamlit page configuration
st.set_page_config(
    page_title="Aurora AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

###################################################### Google Sheets Connection #######################################
# Establish a connection to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)
# Read the data from Google Sheets
feedback_df = conn.read(worksheet="Feedback", ttl=60)
query_df = conn.read(worksheet="Query", ttl=60)
user_df = conn.read(worksheet="UserLogin", ttl=60)

###################################################### User Authentication ######################################################

# Loading config file
with open('config.yaml', 'r', encoding='utf-8') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Initialize session state for register page
if 'register' not in st.session_state:
    st.session_state['register'] = False

def show_login_form():
    # Creating the authenticator object
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        # config['register_user']
    )
    
    # Creating a login widget
    try:
        authenticator.login()
    except LoginError as e:
        st.error(e)
    
    if st.session_state["authentication_status"]:
        authenticator.logout('Logout',"sidebar")
        st.sidebar.write(f'Welcome **{st.session_state["name"]}**👋')
    elif st.session_state["authentication_status"] is False:
        st.error('Username/password is incorrect')
    elif st.session_state["authentication_status"] is None:
        st.warning('Please enter your username and password')

    # Only show the "Register" button if the user is NOT logged in
    if st.session_state["authentication_status"] is None or st.session_state["authentication_status"] == False:
        st.write("---")
        if st.button("Register"):
            st.session_state['register'] = True  # Switch to register page

# Define function to show the register form
def show_register_form():
    st.write("## Register")
    new_username = st.text_input("Enter a new username")
    new_name = st.text_input("Enter your full name")
    new_password = st.text_input("Enter a new password", type="password")
    new_email = st.text_input("Enter your email")

    if st.button("Submit Registration"):
        if new_username and new_password and new_email:
            # Hash the new password
            # hashed_password = Hasher().generate(new_password)[0]
            hashed_password = Hasher([new_password]).hash(new_password)
            if 'credentials' not in config:
                config['credentials'] = {}
            if 'usernames' not in config['credentials']:
                config['credentials']['usernames'] = {}
                
             # Update the config dictionary
            config['credentials']['usernames'][new_username] = {
                'name': new_name,
                'password': hashed_password,
                'email': new_email
            }
        
            # Save the updated credentials to the config.yaml file
            with open('config.yaml', 'w') as file:
                yaml.dump(config, file)
                
            user_data = pd.DataFrame({
                            "Username": new_username,
                            "Name": new_name,
                            "Email": new_email,
                            "Hash_pass": hashed_password
                        }, index=[0])
                    
            # Update the user data
            updated_df = pd.concat([user_df, user_data], ignore_index=True)

            # Update Google Sheets with new User Data
            conn.update(worksheet="UserLogin", data=updated_df)
            st.success("User registered successfully! You can now log in.")
            st.session_state['register'] = False  # Go back to login page
        else:
            st.error("Please fill out all fields")

    # Add a "Back to Login" button to return to the login page
    if st.button("Back to Login"):
        st.session_state['register'] = False  # Return to login page

# Main section: Show either login or register form based on state
if st.session_state['register']:
    show_register_form()  # Show register form
else:
    show_login_form()  # Show login form

###################################################### AI Models ######################################################
# Gemini API
load_dotenv()
# Authenticate with Gemini API
with st.sidebar:
    genai_api_key = st.text_input("Enter your Gemini API Key:", type="password", placeholder="Enter API Key" ,key='api_key')
if genai_api_key is None:
    st.error("Please enter your Gemini API Key.")
    st.stop()
genai.configure(api_key=genai_api_key)

# Load the generative model
model = genai.GenerativeModel('gemini-1.5-flash')

# Generation config for the chatbot
config = genai.types.GenerationConfig(temperature=1.0, max_output_tokens=1500, top_p=0.95, top_k=64)
config_for_chatbot = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain"
}
model_for_chatbot = genai.GenerativeModel(model_name='gemini-1.5-flash',generation_config=config_for_chatbot)



###################################################### Functions ######################################################
# Function for loading csv format file
@st.cache_data
def load_csv_format(file):
        df = pd.read_csv(file)
        return df
    
# Function for loading xlsx format file
@st.cache_data
def load_xlsx_format(file):
        df = pd.read_excel(file)
        return df

# Function for loading file based on its format
@st.cache_data
def load_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
            return load_csv_format(uploaded_file)
    elif uploaded_file.name.endswith('.xlsx'):
            return load_xlsx_format(uploaded_file)
    else:
        st.error("Unsupported file format. Please upload a CSV or XLSX file.")

@st.cache_data
# Function for data cleaning
def df_cleaning(df):
    df = df.drop_duplicates()

    # Impute missing values
    # Seperate numerical and object columns
    numerical_columns = df.select_dtypes(include=['int64', 'float64']).columns
    object_columns = df.select_dtypes(include=['object']).columns

    # Impute missing values for numerical columns and object columns
    numerical_imputer = SimpleImputer(strategy='mean')
    df[numerical_columns] = numerical_imputer.fit_transform(df[numerical_columns])

    object_imputer = SimpleImputer(strategy='most_frequent')
    df[object_columns] = object_imputer.fit_transform(df[object_columns])
    return df

# Function for lottie file
def load_lottie_file(filepath: str):
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)

# Function for generating report
@st.cache_data
def generate_report(df,file):
    # Generate profiling report
    profile = ProfileReport(df, title="Dataset Report", explorative=True)

    # Save the report as an HTML file
    output_path = os.path.join("reports", f"{file.name.split('.')[0]}_report.html")
    profile.to_file(output_path)
    return output_path

# Function for uploading file to Gemini
# @st.cache_data
def upload_to_gemini(path, mime_type=None):
    file = genai.upload_file(path, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file

def wait_for_files_active(files):
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            file = genai.get_file(name)
            if file.state.name != "ACTIVE":
                raise Exception(f"File {file.name} failed to process")

# Function for extracting csv data
@st.cache_data
def extract_csv_data(pathname: str) -> list[str]:
  parts = [f"---START OF CSV ${pathname} ---"]
  with open(pathname, "r", newline="") as csvfile:
    reader = csv.reader(csvfile)
    for row in reader:
      str=" "
      parts.append(str.join(row))
  return parts

###################################################### Page 1: Introduction Page ######################################################
def introduction():
    st.header('🤖Aurora: AI Powered Automated Data Analytics Tool', divider='rainbow')
    
    with st.container(border=False):
        left_column, right_column = st.columns(2)
        with left_column:
            st.subheader("Introduction", divider='rainbow')
            intro_text = ('''
                        - **Aurora AI** is an AI-powered data analytics tool that provides a user-friendly interface for data cleaning, statistical analysis, data visualization, AI powered recommendations, automated data report generation and AI-powered dataset chatbot.
                        - It is designed to help users with little to no programming experience to perform complex data analysis tasks with ease.
                        - The tool is built using Python, Streamlit, and Gemini API for AI-powered content generation.
                        - It offers a wide range of features to help users explore, analyze, and gain insights from their data.
                        - The tool is equipped with AI models that can generate data visualizations, recommendation models, and automated data report generation based on user input.
                    ''')
            st.markdown(intro_text)

        with right_column:
            robot_file = load_lottie_file('animations_and_audios/robot.json')
            st_lottie.st_lottie(robot_file, key='robot', height=450, width=450 ,loop=True)
    st.divider()

    with st.container(border=False):
        left_column, right_column = st.columns(2)
        with right_column:
            st.subheader("Features:", divider='rainbow')
            feature_text = ('''
                        - **CleanStats:** A feature for data cleaning and statistical analysis. Where you can clean the data and get the basic statistics.
                        - **AutoViz:** A feature for data visualization and EDA. Where you can visualize the data using different plots.
                        - **FutureCast AI:** A feature for AI-based recommendations. Where you can get present and future insights based on the dataset.
                        - **InsightGen:** A feature for generating automated data reports. Where you can download the report in interactive HTML format.
                        - **SmartQuery:** A feature for AI-powered dataset chatbot. Where you can chat with the CSV data file and get the response.
                        - **VisionFusion:** A feature for AI-powered image analysis. Where you can analyze the images using AI models.''')
            st.markdown(feature_text)
        
        with left_column:
            features = load_lottie_file('animations_and_audios/features.json')
            st_lottie.st_lottie(features, key='features', height=400, width=400 ,loop=True)
    st.divider()

    with st.container(border=False):
        left_column, right_column = st.columns(2)
        with left_column:
            st.subheader('How To Get Gemini API Key?', divider='rainbow')
            st.markdown('''
                        - **Step 1:** Go to [Google AI Studio](https://aistudio.google.com/app/apikey) and sign up for an account.
                        - **Step 2:** After signing up, click on "Create API Key".
                        - **Step 3:** Select exsisting project or create a "New Project" on [Google Cloud Platform](https://console.cloud.google.com/).
                        - **Step 4:** After selecting the project, click on "Create API key in existing  project" to generate the API Key.
                        - **Step 5:** Copy the API Key and paste it in the Gemini API Key input box in the sidebar.
                        - **Step 6:** Now, you are ready to use the Aurora AI tool for data analysis.
                        - **Refrence YouTube Link:** [How to get Gemini API Key?](https://youtu.be/o8iyrtQyrZM?si=rbEusy-s0l94Lazn)
                        ''')
            st.warning("It is important to keep your API key secure and not share it with anyone.",icon="ℹ️")
        with right_column:
            gemini_logo = load_lottie_file('animations_and_audios/gemini_logo.json')
            st_lottie.st_lottie(gemini_logo, key='logo', height=400, width=400 ,loop=True)
    st.divider()
    
    # Demo Video
    # st.subheader("Demo Video:", divider='rainbow')
    # pass
    # st.divider()
    # FAQ's Section
    with st.container(border=True):
        st.subheader("FAQs:", divider='rainbow')
        # FAQ 1
        with st.expander("What kind of datasets can I upload?"):
            st.markdown("""
            **Ans:** You can upload datasets in CSV or XLSX format. Ensure the dataset has well-defined headers for better analysis.
            Datasets should not contain invalid data.
            """)

        # FAQ 2
        with st.expander("How do I get a Gemini API key?"):
            st.markdown("""
            **Ans:** To get a Gemini API key:
            1. Sign up for a Gemini account on the official website.
            2. Navigate to the API section in your profile.
            3. Generate an API key and copy it for use in the app.
            """)

        # FAQ 3
        with st.expander("What statistical methods are available?"):
            st.markdown("""
            **Ans:** We currently support:
            - Descriptive statistics (mean, median, mode, etc.)
            - Skewness and Kurtosis
            - Correlation analysis
            - And more to come soon!
            """)

        # FAQ 4
        with st.expander("Can I download the analysis report?"):
            st.markdown("""
            **Ans:** Yes, after generating the analysis, you will have the option to download the report as a HTML file for future reference.
            """)

        # FAQ 5
        with st.expander("How secure is my data?"):
            st.markdown("""
            **Ans:** We take data security seriously and ensure that your data is encrypted and stored securely. We do not share your data with third parties.
            """)
        
        # FAQ 6
        with st.expander("How can I provide feedback or report issues?"):
            st.markdown("""
            **Ans:** You can provide feedback or report issues by navigating to the 'Contact Us' section in the sidebar and filling out the form.
            """)
    # st.divider()

###################################################### Page 2: Statistical Analysis ######################################################
def statistical_analysis():
    st.header('🧹CleanStats: Cleaning & Statistical Analysis', divider='rainbow')
    # Upload dataset
    with st.form(key='data_cleaning_form'):
        st.write('Upload a dataset for cleaning and statistical analysis:')
        # Upload dataset
        uploaded_file = st.file_uploader("Upload a dataset", type=["csv", "xlsx"])

        # Submit button
        submitted = st.form_submit_button("Submit")
        if submitted:
            st.success("File uploaded successfully!")

    if uploaded_file is not None:
    # Load the file based on its format
        df = load_file(uploaded_file)
        with st.spinner("Processing..."):
            if df is not None:
            # Remove duplicate rows
                df_cleaning(df)

                # Display dataset
                st.subheader("Dataset Preview:", divider='rainbow')
                st.dataframe(df)
                st.write("*Note: The dataset has been cleaned and missing values have been imputed. You can download the cleaned dataset for further analysis.*")
                
                # Basic statistics
                st.subheader("Basic Statistics:", divider='rainbow')
                st.write("For numerical columns:")
                st.write(df.describe().transpose())

                st.write("For categorical columns:")
                st.write(df.describe(include='object').transpose())

                # Correlation analysis for numerical columns
                st.subheader("Correlation Analysis:", divider='rainbow')
                numerical_columns = df.select_dtypes(include=['int64', 'float64']).columns
                correlation_matrix = df[numerical_columns].corr()
                st.write(correlation_matrix)

                # Skewness and Kurtosis for numerical columns
                st.subheader("Skewness and Kurtosis:", divider='rainbow')
                skewness = df.skew(numeric_only=True)
                kurtosis = df.kurt(numeric_only=True)
                skew_kurt_df = pd.DataFrame({
                    'Skewness': skewness,
                    'Kurtosis': kurtosis
                })
                st.write(skew_kurt_df)

                # Unique Values Count
                st.subheader("Unique Values Count:", divider='rainbow')
                col1, col2 = st.columns(2)
                col1.write("Categorical columns unique values:")
                col1.write(df.select_dtypes(include=['object']).nunique())
                col2.write("Numerical columns unique values:")
                col2.write(df.select_dtypes(include=[np.number]).nunique())
                st.success("Data Cleaning & Statistical Analysis completed successfully!")

###################################################### Page 3: Data Visualization ######################################################
def data_visualization():
    st.header('📈AutoViz: Data Visualization & EDA', divider='rainbow')
    # Create a form for uploading the dataset, selecting the visualization type, and entering the columns
    with st.form(key='data_visualization_form'):
        st.write("Upload a dataset to generate visualizations.")
        # Upload dataset
        uploaded_file = st.file_uploader("Choose a file")
        
        # Select the visualization type
        visualization_type = st.selectbox("Select the visualization type", ["Bar Chart", "Line Chart", "Scatter Plot", "Histogram", "Box Plot", "Heatmap", "Pie Chart", "Violin Plot", "Count Plot",  "KDE Plot"])
        
        # Enter the columns for visualization
        user_input = st.text_input("Enter the columns for visualization separated by 'and', Example: column1 and column2")
        
        # Submit button
        submitted = st.form_submit_button("Submit")
        if submitted:
            st.success("File and visualization type submitted successfully!")
    
    with st.spinner("Generating Visualization..."):
        # Check if the file, visualization type, and user input are provided before generating the visualization
        if uploaded_file and visualization_type and user_input is not None:
            # Get file name and path
            file_name = uploaded_file.name
            file_path = os.path.join("uploads", file_name)

            # Load the file based on its format and clean the data
            df = load_file(uploaded_file)
            df = df_cleaning(df)

            # Extract a sample of the dataset for model understanding
            df_sample = str(df.head())
            # Columns for visualization
            columns = user_input
            
            # Add a subheader for the visualization
            st.subheader(f"{visualization_type} Visualization for the dataset '{file_name}' for the columns {columns}:")
            
            # Provide a predefined prompt for the model
            predefined_prompt = f"""Write a python code to plot a {visualization_type} using Matplotlib or Seaborn Library. Name of the dataset is {file_name}.
            Plot for the dataset columns {columns}. Here's the sample of dataset {df_sample}. Set xticks rotation 90 degree. 
            Set title in each plot. Add tight layout in necessary plots. Don't right the explanation, just write the code."""
            
            # Generate the code for the visualization
            response = model.generate_content(predefined_prompt, generation_config=config)
            generated_code = response.text
            generated_code = generated_code.replace("```python", "").replace("```", "").strip()
            
            # Modify the code to insert the actual file path into pd.read_csv()
            if "pd.read_csv" in generated_code:
                generated_code = generated_code.replace("pd.read_csv()", f'pd.read_csv(r"{file_path}")')
            elif "pd.read_excel" in generated_code:
                generated_code = generated_code.replace("pd.read_excel()", f'pd.read_excel(r"{file_path}")')

            # Display the generated code
            st.code(generated_code, language='python')

            # Execute the generated code to plot the visualization
            try:
                exec(generated_code)
                st.pyplot(plt.gcf())
            except Exception as e:
                st.error(e)
            st.success("Visualization generated successfully!")

###################################################### Page 4: AI Based Recommendations ######################################################
def ai_recommendation():
    st.header('🔮FutureCast AI: AI Recommendation Based On Dataset', divider='rainbow')
    # Upload dataset
    st.write('Upload a dataset to predict:')
    uploaded_file = st.file_uploader("Upload a dataset", type=["csv"])
    if uploaded_file is not None:
        st.success("File uploaded successfully!")
        type_of_recommendation = st.radio("Type of Recommendation", ["Present Insight", "Future Insight"])
        if st.button("Submit"):
            with st.spinner("Processing..."):
                file_name = uploaded_file.name
                st.subheader("Recommendation:")
                file_path = os.path.join(os.getcwd(), file_name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                # Upload the file to Gemini and wait for it to be active
                files = [upload_to_gemini(file_name, mime_type="text/csv")]
                wait_for_files_active(files)
                # Start a chat session with the uploaded file
                chat_session = model.start_chat(
                history=[
                    {
                    "role":"user",
                    "parts":extract_csv_data(file_name)
                    },
                ]
                )
                # Send the question
                question = f""""Provide {type_of_recommendation} based on the dataset {file_name}. If dataset is related to financial or healthcare 
                , just give your best recommendation, don't think about advisor or expertise thing. Mention also 
                that recommendation is generated by AI, first give your essential recommendations. So, the user take the final decision on 
                their own. Warn user about AI recommendation but, do your work."""
                response = chat_session.send_message(question)
                st.write(response.text)
                st.success("Recommendation generated successfully!")

###################################################### Page 5: Analysis Report ######################################################
def analysis_report():
    st.header('📑InsightGen: Automated Data Report Generator', divider='rainbow')
    # Upload dataset
    st.write('Upload a dataset to generate a report:')
    uploaded_file = st.file_uploader("Upload a dataset", type=["csv", "xlsx"])
    if uploaded_file is not None:
        if st.button("Submit"):
            with st.spinner("Processing..."):
                filename = uploaded_file.name
                df = load_file(uploaded_file)
                st.success("File uploaded successfully!")
                if df is not None:
                    # Gemini Text Report Generation
                    summary = df.describe().transpose().to_string()
                    prompt = f"""Generate a text report for {filename} dataset using Gemini AI. Here's the summary of the dataset: {summary}.
                            Try to make the report in bullet points and use numbers for better readability and understanding."""
                    response = model.generate_content(prompt, generation_config=config)
                    generated_report = response.text
                    st.write(generated_report)
                    st.success("Report generated successfully!")

            st.write("Wait for the report to be generated...")
            with st.spinner("Generating Report..."):
                # Generate a report in HTML format for download
                report_path = generate_report(df, uploaded_file)
                with open(report_path, 'rb') as f:
                    st.download_button(
                        label="Download Report",
                        data=f,
                        file_name=f"{uploaded_file.name.split('.')[0]}_report.html",
                        mime="text/html"
                    )

###################################################### Page 6: Dataset ChatBot ######################################################
def ai_data_file_chatbot():
    st.header('🤖SmartQuery: AI Powered Dataset ChatBot', divider='rainbow')
    # Upload dataset
    st.write('Upload a dataset to chat with data file:')
    uploaded_file = st.file_uploader("Upload a dataset", type=["csv"])
    if uploaded_file is not None:
        st.success("File uploaded successfully!")
        # Get the user question
        question = st.text_input("Ask a question:", key="question")
        if st.button("Submit"):
            with st.spinner("Processing..."):
                file_name = uploaded_file.name
                st.subheader("ChatBot Response:")
                file_path = os.path.join(os.getcwd(), file_name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Upload the file to Gemini and wait for it to be active
                files = [upload_to_gemini(file_name, mime_type="text/csv")]
                wait_for_files_active(files)
                # Start a chat session with the uploaded file
                chat_session = model.start_chat(
                history=[
                    {
                    "role":"user",
                    "parts":extract_csv_data(file_name)
                    },
                ]
                )
                # Send the user question to the chatbot for response
                response = chat_session.send_message(question)
                st.write(response.text)

###################################################### Page 7: Vision Analysis ######################################################
def vision_analysis():
    st.header('👁️VisionFusion: AI-Powered Image Analysis ', divider='rainbow')
    # Upload image
    st.write('Upload an image to analyze:')
    uploaded_image = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])
    if uploaded_image is not None:
        # Show uploaded image
        st.image(uploaded_image, caption="Uploaded Image", use_column_width=False)
        st.success("Image uploaded successfully!")
        user_query = st.text_input("Ask a query:")
        if st.button("Submit"):
            with st.spinner("Processing..."):
                file_name = uploaded_image.name
                st.subheader(f"'{file_name}' Image Analysis:")
                st.divider()
                image = Image.open(uploaded_image)
                prompt = f"Analyze the image and provide a detailed description of the image. {user_query}"
                response = model.generate_content([prompt,image], stream=True)
                response.resolve()
                st.write(response.text)
                st.success("Image analyzed successfully!")

###################################################### Page 8: Contact Us ####################################################
def contact_us():
    st.header('📧Contact Us', divider='rainbow')
    st.subheader("Have a query 🤔 or feedback 😀? Reach out to us ⬇️!", divider='rainbow')

    # Select the action
    action = st.selectbox("Select an action:", ["Query", "Feedback"])
    # Contact Form
    if action == "Feedback":
        with st.form(key='contact_form'):
            name = st.text_input("Name*", key='user_name')
            email = st.text_input("Email*", key='user_email')
            ratings = st.radio("Ratings*", [1, 2, 3, 4, 5], key='rating')
            message = st.text_area("Message*", key='message')
            st.markdown("**Required*")
            submit_button = st.form_submit_button("Submit")
            if submit_button:
                if not name or not email or not message:
                    st.error("Please fill in the required fields.")
                    st.stop()
                else :
                    feedback_df["Email"] = feedback_df["Email"].astype(str) 
                    if feedback_df["Email"].str.contains(email).any():
                        st.warning("You have already submitted a feedback.")
                        st.stop()
                    else:
                        user_feedback_data = pd.DataFrame({
                            "Name": name,
                            "Email": email,
                            "Ratings": ratings,
                            "Message": message
                        }, index=[0])
                    
                        # Update the feedback data
                        updated_df = pd.concat([feedback_df, user_feedback_data], ignore_index=True)

                        # Update Google Sheets with new Feedback Data
                        conn.update(worksheet="Feedback", data=updated_df)
                        st.success("Feedback submitted successfully!")

    if action == "Query":
        with st.form(key='contact_form'):
            name = st.text_input("Name*", key="user_name")
            email = st.text_input("Email*", key="user_email")
            subject = st.text_input("Subject*", key="subject")
            message = st.text_area("Message*", placeholder="Explain your query in detail.", key="message")
            check_box = st.checkbox("I agree to be contacted for further details.", key="check_box")
            st.markdown("**Required*")
            submit_button = st.form_submit_button("Submit")
            if submit_button:
                if not name or not email or not subject or not message:
                    st.error("Please fill in the required fields.")
                    st.stop()
                elif not check_box:
                    st.error("Please agree to be contacted for further details.")
                    st.stop()
                else:
                    query_df["Email"] = query_df["Email"].astype(str)                 
                    if query_df["Email"].str.contains(email).any():
                      st.warning("You have already submitted a query.")
                      st.stop()
                    else:
                        user_query_data = pd.DataFrame({
                            "Name": name,
                            "Email": email,
                            "Subject": subject,
                            "Message": message
                        }, index=[0])
                        
                        # Update the query data
                        updated_df = pd.concat([query_df, user_query_data], ignore_index=True)

                        # Update Google Sheets with new Query Data
                        conn.update(worksheet="Query", data=updated_df)
                        st.success("Query submitted successfully!")
            
###################################################### Page 8: About Us ######################################################
def about_us():
    st.header('👨‍💻About Us: Meet Team Aurora', divider='rainbow')
    
    with st.container(border=True):
        left_column, right_column = st.columns(2)
        with left_column:
            st.subheader("Anubhav Yadav", divider='rainbow')
            st.markdown('''
                        - **Role:** Lead Developer
                        - **Email:** [![Anubhav Email](https://img.icons8.com/color/30/email.png)](yadavanubhav2024@gmail.com)
                        - **LinkedIn:** [![Anubhav Yadav LinkedIn](https://img.icons8.com/color/30/linkedin.png)](https://www.linkedin.com/in/anubhav-yadav-data-science/)
                        - **GitHub:** [![Anubhav Yadav GitHub](https://badgen.net/badge/icon/GitHub?icon=github&label)](https://www.github.com/AnubhavYadavBCA25)
                        - **Bio:** Anubhav is a Data Science Enthusiast with a passion for building AI-powered applications. He is skilled in 
                                    Python, Machine Learning, and Data Analysis. He is currently pursuing a Bachelor's degree in Computer Applications 
                                    specializing in Data Science.
                        ''')
        with right_column:
            anubhav_profile = load_lottie_file('profile_animations/anubhav_profile.json')
            st_lottie.st_lottie(anubhav_profile, key='anubhav', height=305, width=305 ,loop=True, quality='high')
    st.divider()

    # Footer
    st.markdown(
    """
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
    <div style="text-align:center;">
        <p>Made with ❤️ by Team Aurora @2024</p>
    </div>
    """, unsafe_allow_html=True
)

###################################################### Navigation ######################################################
if st.session_state["authentication_status"]:
    pg = st.navigation([
        st.Page(introduction, title='Home', icon='🏠'),
        st.Page(statistical_analysis, title='CleanStats', icon='🧹'),
        st.Page(data_visualization, title='AutoViz', icon='📈'),
        st.Page(ai_recommendation, title='FutureCast AI', icon='🔮'),
        st.Page(analysis_report, title='InsightGen', icon='📑'),
        st.Page(ai_data_file_chatbot, title='SmartQuery', icon='🤖'),
        st.Page(vision_analysis, title='VisionFusion', icon='👁️'),
        st.Page(contact_us, title='Contact Us', icon='📧'),
        st.Page(about_us, title='About Us', icon='👨‍💻')
    ])
    pg.run()