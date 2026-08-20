# Py_Hostel - Smart Hostel Management System

Py_Hostel is a comprehensive, web-based hostel management system built as a Database Lab project. It is designed to digitize and streamline the everyday operations of a hostel, enhancing communication, transparency, and administration across different levels of users.

## 🚀 Features by User Role

### 1. Admin
The Admin acts as the ultimate supervisor and manager of the hostel system.
- **Role Registration:** Admins register via a secure, secret-key protected interface.
- **Room Management:** Add, configure, and delete hostel rooms. Assign capacity limits and optional teachers to specific rooms.
- **Student Assignments:** Handle allocating registered students to available rooms without exceeding capacity limits.
- **Food Management:** Control the hostel's menu. Add food items categorically (Veg and Non-Veg) with pricing.
- **Oversight & Moderation:** 
  - Manage and review student complaints.
  - Review and update maintenance requests (Pending, In Progress, Resolved).
  - Publish role-based Notice Board announcements from a dedicated admin panel.
  - View all student food orders and system-wide stats.

### 2. Teacher
A Teacher serves as a block/room supervisor, ensuring discipline and addressing room-specific student issues.
- **Room Monitoring:** View details of rooms assigned to them, including the occupancy and the students residing there.
- **Complaint Handling:** Review and resolve complaints specific to their assigned rooms. Features an expandable drop-down for reading lengthy complaints clearly.
- **Direct Communication:** Interact directly with students under their supervision via a real-time Chat System.
- **Live Alerts:** Receive role-based notifications for complaint and maintenance activities in the Alerts Center.

### 3. Student
Students are the primary consumers of the system's utilities.
- **Dashboard & Tracking:** Students have a dashboard tracking their assigned room, food order history, and pending dues.
- **Meal Ordering:** Order food directly from the dynamically created menu. Ordered meals automatically generate pending payment receipts.
- **Payments & Receipts:** Keep track of unpaid dues (Meals, Hall Fees, etc.). Once marked as paid, students can generate and download a PDF version of their receipt.
- **Complaints & Maintenance:** Transparently file complaints (with an option to remain anonymous) and request room maintenance directly to the admins/teachers.
- **Reading Room Booking:** Book hourly slots in the hostel’s communal reading room to reserve a study space.
- **Real-time Chatting:** Chat directly (real-time) with their assigned teacher regarding any disputes or issues using the integrated Socket.IO interface.
- **Alerts Center:** View personal notifications and shared Notice Board updates in a unified panel.

### 4. Shared Notification & Notice Board
- **Alerts Center Panel:** Available across authenticated pages for Admin, Teacher, and Student.
- **Personal Notifications:** Tracks role-specific operational updates like assignments, complaint reviews, maintenance status, and payment events.
- **Notice Board Feed:** Displays admin-published announcements filtered by role target (`All`, `Admin`, `Teacher`, `Student`).
- **Read Management:** Users can mark single notifications or all notifications as read.

---

## 🛠 Tech Stack
- **Backend:** Python, Flask, Flask-SocketIO
- **Database:** MySQL (Structured via local XAMPP/MySQL Workbench environment)
- **Frontend:** HTML, CSS, Jinja2 templating, JavaScript
- **Libraries:** PyMySQL (DB connection), PDFkit (PDF generation)

---

## ⚙️ Installation & Setup (How to run locally)

Follow these steps to deploy and run Py_Hostel on your local machine:

### Prerequisites:
1. Python 3.8+
2. MySQL Server (or XAMPP)
3. MySQL Workbench (Optional but recommended for database viewing)
4. *wkhtmltopdf* (Required for the Student PDF Receipt Generation feature to work. [Download here](https://wkhtmltopdf.org/downloads.html))

### 1. Set Up the Database
Open your MySQL Workbench (or CLI) and run the provided SQL script:
- Create a local database connection (Default user `root`, change password inside `app.py` if necessary).
- Execute the contents of `schema.sql` completely to build the `nasa_home` database, tables, and insert dummy data.

### 2. Install Python Dependencies
Open a terminal in the root directory of the project and install the required modules:
```bash
pip install -r requirements.txt
```
*(If you do not have a requirements file, install manually):*
```bash
pip install Flask Flask-SocketIO PyMySQL pdfkit eventlet
```

### 3. Configure Database Connection 
Open `app.py` and modify the following block to match your local MySQL credentials:
```python
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'your_mysql_password_here'  # e.g., 'pass123' or blank '' for XAMPP
DB_NAME = 'nasa_home'
```

### 4. Run the Server
Launch the Flask development server via your terminal:
```bash
python app.py
```

### 5. Open in Browser
Open your favorite web browser and go to your localhost URL:
```text
http://127.0.0.1:5000/
```

- **Login:** Use the pre-loaded users in the `schema.sql` or register a new one. 
- **Admin Setup:** While registering an Admin, ensure you use the secret code: `XXXXXXXX` _(collect the secret code from the owner)_