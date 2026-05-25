import streamlit as st
import pandas as pd
import numpy as np
import mysql.connector
import os
from dotenv import load_dotenv
import openai
import speech_recognition as sr
from datetime import datetime

# Load environment variables
load_dotenv()

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Page configuration
st.set_page_config(
    page_title="Exam Seating Visualizer",
    page_icon="🎓",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .seat {
        padding: 10px;
        margin: 5px;
        border-radius: 5px;
        text-align: center;
        
    }
    .empty {
        background-color: #f0f0f0;
    }
    .occupied {
        background-color: #90EE90;
    }
    .special {
        background-color: #FFB6C1;
    }
</style>
""", unsafe_allow_html=True)

def fetch_exams():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, date FROM seating_exam ORDER BY date DESC")
    exams = cursor.fetchall()
    cursor.close()
    conn.close()
    return exams

def fetch_room_layout(exam_id, room_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get room dimensions
    cursor.execute("""
        SELECT rows, columns 
        FROM seating_room 
        WHERE id = %s
    """, (room_id,))
    room = cursor.fetchone()
    
    # Get allocations
    cursor.execute("""
        SELECT sa.row, sa.column, s.name, s.roll_number, b.code as branch_code,
               s.needs_accommodation
        FROM seating_seatallocation sa
        JOIN seating_examroom er ON sa.exam_room_id = er.id
        JOIN seating_student s ON sa.student_id = s.id
        JOIN seating_branch b ON s.branch_id = b.id
        WHERE er.exam_id = %s AND er.room_id = %s
    """, (exam_id, room_id))
    allocations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return room, allocations

def display_room_layout(room, allocations):
    grid = [[None for _ in range(room['columns'])] for _ in range(room['rows'])]
    
    # Fill grid with allocations
    for alloc in allocations:
        grid[alloc['row']][alloc['column']] = alloc
    
    # Create columns for the grid
    cols = st.columns(room['columns'])
    
    # Display seats
    for row in range(room['rows']):
        for col in range(room['columns']):
            with cols[col]:
                student = grid[row][col]
                if student:
                    css_class = 'special' if student['needs_accommodation'] else 'occupied'
                    st.markdown(f"""
                        <div class='seat {css_class}'>
                            <strong>{student['roll_number']}</strong><br>
                            {student['name']}<br>
                            <small>{student['branch_code']}</small>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                        <div class='seat empty'>
                            Empty
                        </div>
                    """, unsafe_allow_html=True)

def chat_with_ai(query):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for an exam seating allocation system."},
                {"role": "user", "content": query}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def voice_to_text():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        st.write("Listening... Speak now!")
        try:
            audio = r.listen(source, timeout=5)
            text = r.recognize_google(audio)
            return text
        except sr.WaitTimeoutError:
            return "No speech detected"
        except sr.UnknownValueError:
            return "Could not understand audio"
        except sr.RequestError:
            return "Could not request results"

# Main app
def main():
    st.title("🎓 Exam Seating Visualizer")
    
    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Seating Layout", "AI Assistant"])
    
    if page == "Seating Layout":
        # Exam selection
        exams = fetch_exams()
        exam_options = {f"{exam['name']} ({exam['date']}": exam['id'] for exam in exams}
        selected_exam = st.selectbox("Select Exam", list(exam_options.keys()))
        
        if selected_exam:
            exam_id = exam_options[selected_exam]
            
            # Room selection
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT r.id, r.name
                FROM seating_room r
                JOIN seating_examroom er ON r.id = er.room_id
                WHERE er.exam_id = %s
            """, (exam_id,))
            rooms = cursor.fetchall()
            cursor.close()
            conn.close()
            
            room_options = {room['name']: room['id'] for room in rooms}
            selected_room = st.selectbox("Select Room", list(room_options.keys()))
            
            if selected_room:
                room_id = room_options[selected_room]
                room, allocations = fetch_room_layout(exam_id, room_id)
                
                st.subheader(f"Room Layout: {selected_room}")
                display_room_layout(room, allocations)
                
                # Export options
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Export to PDF"):
                        st.info("PDF export functionality to be implemented")
                with col2:
                    if st.button("Export to Excel"):
                        st.info("Excel export functionality to be implemented")
    
    else:  # AI Assistant page
        st.header("🤖 AI Assistant")
        st.write("Ask questions about seating arrangements or get help with the system.")
        
        # Voice input
        if st.button("🎤 Voice Input"):
            query = voice_to_text()
            if query and not query.startswith("Could not") and not query.startswith("No speech"):
                st.text_area("You said:", query)
        
        # Text input
        query = st.text_input("Type your question:")
        
        if query:
            with st.spinner("Thinking..."):
                response = chat_with_ai(query)
                st.write("Response:", response)

if __name__ == "__main__":
    main() 