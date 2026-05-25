# Exam Seating Automation System

A scalable, web-based system for automating exam seating arrangements using Django, MySQL, and Streamlit.

## Features

- Smart Seating Allocation Engine
- Visual Room Layout Management
- Admin Dashboard
- Role-based Access Control
- Reporting & Exporting (PDF/Excel)
- AI Chatbot Assistant
- Mobile-friendly Interface

## Tech Stack

- Backend: Django
- Frontend: Django Templates + Streamlit
- Database: MySQL
- Authentication: Django Auth
- Export Tools: fpdf2, XlsxWriter
- AI/Voice: OpenAI API, Speech Recognition

## Setup Instructions

1. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure MySQL database settings in `.env` file:
```
DB_NAME=exam_seating
DB_USER=your_username
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306
OPENAI_API_KEY=your_openai_api_key
```

4. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Run the Django development server:
```bash
python manage.py runserver
```

7. Run Streamlit (in a separate terminal):
```bash
streamlit run streamlit_app.py
```

## Project Structure

```
exam_seating/
├── manage.py
├── requirements.txt
├── .env
├── README.md
├── core/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── seating/
│   ├── models.py
│   ├── views.py
│   ├── admin.py
│   ├── forms.py
│   └── utils/
│       ├── allocation.py
│       ├── export.py
│       └── chatbot.py
├── templates/
│   ├── base.html
│   ├── dashboard/
│   └── seating/
├── static/
│   ├── css/
│   ├── js/
│   └── img/
└── streamlit_app.py
```

## Usage

1. Access the admin dashboard at `/admin`
2. Upload student and room data
3. Configure seating parameters
4. Generate and visualize seating arrangements
5. Export reports in PDF/Excel formats

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request 