#!/usr/bin/env python3
"""
FaceGuard Pro - Advanced Face Recognition System with Admin Authentication
Flask Backend Server with API endpoints
"""

import os
import cv2
import numpy as np
import face_recognition
import sqlite3
import base64
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import hashlib
import secrets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FaceRecognitionSystem:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = secrets.token_hex(32)
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
        
        # Initialize directories
        self.create_directories()
        
        # Initialize database
        self.init_database()
        
        # Create default admin if not exists
        self.create_default_admin()
        
        # Load known faces
        self.known_encodings = []
        self.known_names = []
        self.load_known_faces()
        
        # Setup routes
        self.setup_routes()
        
        self.suspicious_pipeline = None
        
        logger.info("FaceGuard Pro initialized successfully")

    def create_directories(self):
        """Create necessary directories if they don't exist"""
        directories = ['database', 'uploads', 'static']
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect('database/faceguard.db')
        cursor = conn.cursor()
        
        # Admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # Users table (recognized faces)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                image_path TEXT NOT NULL,
                encoding_hash TEXT NOT NULL,
                added_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES admin_users (id)
            )
        ''')
        
        # Attendance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence REAL DEFAULT 0.0,
                emotion TEXT DEFAULT 'neutral',
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Sessions table for admin login tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                ip_address TEXT,
                FOREIGN KEY (admin_id) REFERENCES admin_users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def create_default_admin(self):
        """Create default admin account if none exists"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM admin_users')
            count = cursor.fetchone()[0]
            
            if count == 0:
                # Default admin credentials - UPDATED
                default_email = 'kaushik29@gmail.com'
                default_password = 'kaushik123'
                default_name = 'Kaushik Khodke'
                
                password_hash = generate_password_hash(default_password)
                
                cursor.execute('''
                    INSERT INTO admin_users (email, password_hash, name)
                    VALUES (?, ?, ?)
                ''', (default_email, password_hash, default_name))
                
                conn.commit()
                logger.info(f"Default admin created: {default_email}")
                print("\n" + "="*60)
                print("🔐 ADMIN CREDENTIALS")
                print("="*60)
                print(f"Email: {default_email}")
                print(f"Password: {default_password}")
                print("="*60 + "\n")
            
            conn.close()
        except Exception as e:
            logger.error(f"Error creating default admin: {e}")

    def verify_admin_session(self, session_token):
        """Verify admin session token"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT admin_id, expires_at FROM admin_sessions
                WHERE session_token = ? AND expires_at > datetime('now')
            ''', (session_token,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]  # Return admin_id
            return None
        except Exception as e:
            logger.error(f"Session verification error: {e}")
            return None

    def admin_login(self, email, password, ip_address):
        """Authenticate admin user"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, password_hash, name, is_active
                FROM admin_users WHERE email = ?
            ''', (email,))
            
            admin = cursor.fetchone()
            
            if not admin:
                conn.close()
                return {"success": False, "error": "Invalid credentials"}
            
            admin_id, password_hash, name, is_active = admin
            
            if not is_active:
                conn.close()
                return {"success": False, "error": "Account is deactivated"}
            
            if not check_password_hash(password_hash, password):
                conn.close()
                return {"success": False, "error": "Invalid credentials"}
            
            # Create session token
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)
            
            cursor.execute('''
                INSERT INTO admin_sessions (admin_id, session_token, expires_at, ip_address)
                VALUES (?, ?, ?, ?)
            ''', (admin_id, session_token, expires_at, ip_address))
            
            # Update last login
            cursor.execute('''
                UPDATE admin_users SET last_login = datetime('now')
                WHERE id = ?
            ''', (admin_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Admin logged in: {email}")
            
            return {
                "success": True,
                "session_token": session_token,
                "admin_name": name,
                "admin_email": email
            }
            
        except Exception as e:
            logger.error(f"Admin login error: {e}")
            return {"success": False, "error": "Login failed"}

    def admin_logout(self, session_token):
        """Logout admin user"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM admin_sessions WHERE session_token = ?
            ''', (session_token,))
            
            conn.commit()
            conn.close()
            return {"success": True}
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return {"success": False, "error": "Logout failed"}

    def load_known_faces(self):
        """Load known faces from database and image files"""
        try:
            # Load from sample images first
            sample_faces = [
                ("face.jpg", "Siddharth"),
                ("mayu.jpg", "Mayuri")
            ]
            
            for image_file, name in sample_faces:
                if os.path.exists(image_file):
                    image = face_recognition.load_image_file(image_file)
                    encodings = face_recognition.face_encodings(image)
                    if encodings:
                        self.known_encodings.append(encodings[0])
                        self.known_names.append(name)
                        self.add_user_to_db(name, image_file, encodings[0], None)
                        logger.info(f"Loaded face for {name}")
            
            # Load additional faces from database
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, image_path FROM users")
            users = cursor.fetchall()
            
            for name, image_path in users:
                if name not in self.known_names and os.path.exists(image_path):
                    image = face_recognition.load_image_file(image_path)
                    encodings = face_recognition.face_encodings(image)
                    if encodings and name not in self.known_names:
                        self.known_encodings.append(encodings[0])
                        self.known_names.append(name)
                        logger.info(f"Loaded face for {name} from database")
            
            conn.close()
            logger.info(f"Total faces loaded: {len(self.known_names)}")
            
        except Exception as e:
            logger.error(f"Error loading known faces: {e}")

    def add_user_to_db(self, name, image_path, encoding, admin_id):
        """Add user to database"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            encoding_hash = hashlib.md5(encoding.tobytes()).hexdigest()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users (name, image_path, encoding_hash, added_by)
                VALUES (?, ?, ?, ?)
            ''', (name, image_path, encoding_hash, admin_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error adding user to database: {e}")
            return False

    def log_attendance(self, user_name, confidence, emotion="neutral", ip_address=None):
        """Log attendance to database"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM users WHERE name = ?", (user_name,))
            user_result = cursor.fetchone()
            user_id = user_result[0] if user_result else 0
            
            cursor.execute('''
                INSERT INTO attendance (user_id, name, confidence, emotion, ip_address)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, user_name, confidence, emotion, ip_address))
            
            conn.commit()
            conn.close()
            logger.info(f"Attendance logged for {user_name}")
            return True
        except Exception as e:
            logger.error(f"Error logging attendance: {e}")
            return False

    def recognize_face(self, image_data):
        """Recognize face from base64 image data"""
        try:
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if not face_encodings:
                return {"name": "Unknown", "confidence": 0.0, "emotion": "neutral"}
            
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(self.known_encodings, face_encoding, tolerance=0.6)
                name = "Unknown"
                confidence = 0.0
                
                face_distances = face_recognition.face_distance(self.known_encodings, face_encoding)
                
                if len(face_distances) > 0:
                    best_match_index = np.argmin(face_distances)
                    if matches[best_match_index]:
                        name = self.known_names[best_match_index]
                        confidence = 1 - face_distances[best_match_index]
                
                emotion = self.detect_emotion(rgb_frame, face_locations[0] if face_locations else None)
                
                return {
                    "name": name,
                    "confidence": float(confidence),
                    "emotion": emotion,
                    "face_locations": face_locations
                }
            
            return {"name": "Unknown", "confidence": 0.0, "emotion": "neutral"}
            
        except Exception as e:
            logger.error(f"Face recognition error: {e}")
            return {"name": "Unknown", "confidence": 0.0, "emotion": "neutral", "error": str(e)}

    def detect_emotion(self, rgb_frame, face_location):
        """Simple emotion detection"""
        emotions = ["happy", "neutral", "surprised", "focused", "confident"]
        
        if face_location:
            top, right, bottom, left = face_location
            face_area = (right - left) * (bottom - top)
            
            if face_area > 10000:
                return "confident"
            elif face_area > 5000:
                return "happy"
            else:
                return "neutral"
        
        return np.random.choice(emotions)

    def add_new_person(self, name, image_data, admin_id):
        """Add a new person to the recognition system (admin only)"""
        try:
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            filename = secure_filename(f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            image_path = os.path.join('uploads', filename)
            cv2.imwrite(image_path, image)
            
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            face_encodings = face_recognition.face_encodings(rgb_image)
            if not face_encodings:
                return {"success": False, "error": "No face detected in image"}
            
            face_encoding = face_encodings[0]
            
            self.known_encodings.append(face_encoding)
            self.known_names.append(name)
            
            if self.add_user_to_db(name, image_path, face_encoding, admin_id):
                logger.info(f"Successfully added new person: {name}")
                return {"success": True, "message": f"Successfully added {name}"}
            else:
                return {"success": False, "error": "Failed to save to database"}
                
        except Exception as e:
            logger.error(f"Error adding new person: {e}")
            return {"success": False, "error": str(e)}

    def get_attendance_data(self):
        """Get attendance statistics and records"""
        try:
            conn = sqlite3.connect('database/faceguard.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT name, timestamp, confidence, emotion
                FROM attendance
                ORDER BY timestamp DESC
                LIMIT 50
            ''')
            records = cursor.fetchall()
            
            cursor.execute('SELECT COUNT(DISTINCT DATE(timestamp)) FROM attendance')
            total_days = cursor.fetchone()[0] or 0
            
            cursor.execute('''
                SELECT AVG(CAST(strftime('%H', timestamp) AS INTEGER))
                FROM attendance
            ''')
            avg_hour_result = cursor.fetchone()
            avg_hour = avg_hour_result[0] if avg_hour_result[0] else 12
            
            cursor.execute('''
                SELECT DATE(timestamp) as date
                FROM attendance
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
                LIMIT 30
            ''')
            dates = [row[0] for row in cursor.fetchall()]
            
            streak = 0
            if dates:
                current_date = datetime.now().date()
                for i, date_str in enumerate(dates):
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    expected_date = current_date - timedelta(days=i)
                    
                    if date_obj == expected_date:
                        streak += 1
                    else:
                        break
            
            conn.close()
            
            return {
                "success": True,
                "records": [
                    {
                        "name": record[0],
                        "timestamp": record[1],
                        "confidence": record[2],
                        "emotion": record[3]
                    } for record in records
                ],
                "total_days": total_days,
                "avg_time": f"{int(avg_hour):02d}:00",
                "streak": streak
            }
            
        except Exception as e:
            logger.error(f"Error getting attendance data: {e}")
            return {"success": False, "error": str(e)}

    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return send_from_directory('.', 'index.html')
        
        @self.app.route('/<path:filename>')
        def static_files(filename):
            return send_from_directory('.', filename)
        
        @self.app.route('/api/admin/login', methods=['POST'])
        def admin_login_route():
            try:
                data = request.get_json()
                if not data or 'email' not in data or 'password' not in data:
                    return jsonify({"success": False, "error": "Email and password required"})
                
                client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
                result = self.admin_login(data['email'], data['password'], client_ip)
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Admin login route error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/admin/logout', methods=['POST'])
        def admin_logout_route():
            try:
                data = request.get_json()
                session_token = data.get('session_token')
                
                if not session_token:
                    return jsonify({"success": False, "error": "Session token required"})
                
                result = self.admin_logout(session_token)
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Admin logout route error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/admin/verify', methods=['POST'])
        def verify_admin_route():
            try:
                data = request.get_json()
                session_token = data.get('session_token')
                
                if not session_token:
                    return jsonify({"success": False, "error": "Session token required"})
                
                admin_id = self.verify_admin_session(session_token)
                
                if admin_id:
                    return jsonify({"success": True, "admin_id": admin_id})
                else:
                    return jsonify({"success": False, "error": "Invalid or expired session"})
                
            except Exception as e:
                logger.error(f"Verify admin route error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/recognize', methods=['POST'])
        def recognize():
            try:
                data = request.get_json()
                if not data or 'image' not in data:
                    return jsonify({"success": False, "error": "No image data provided"})
                
                result = self.recognize_face(data['image'])
                
                if result['name'] != 'Unknown':
                    client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
                    self.log_attendance(
                        result['name'],
                        result['confidence'],
                        result.get('emotion', 'neutral'),
                        client_ip
                    )
                
                return jsonify({
                    "success": True,
                    "name": result['name'],
                    "confidence": result['confidence'],
                    "emotion": result.get('emotion', 'neutral')
                })
                
            except Exception as e:
                logger.error(f"Recognition API error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/add_person', methods=['POST'])
        def add_person():
            try:
                data = request.get_json()
                
                # Verify admin session
                session_token = data.get('session_token')
                if not session_token:
                    return jsonify({"success": False, "error": "Admin authentication required"})
                
                admin_id = self.verify_admin_session(session_token)
                if not admin_id:
                    return jsonify({"success": False, "error": "Invalid or expired session"})
                
                if not data or 'name' not in data or 'image' not in data:
                    return jsonify({"success": False, "error": "Name and image required"})
                
                result = self.add_new_person(data['name'], data['image'], admin_id)
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Add person API error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/attendance', methods=['GET'])
        def attendance():
            try:
                data = self.get_attendance_data()
                return jsonify(data)
                
            except Exception as e:
                logger.error(f"Attendance API error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/users', methods=['GET'])
        def get_users():
            try:
                conn = sqlite3.connect('database/faceguard.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id, name, created_at FROM users ORDER BY name')
                users = cursor.fetchall()
                conn.close()
                
                return jsonify({
                    "success": True,
                    "users": [
                        {
                            "id": user[0],
                            "name": user[1],
                            "created_at": user[2]
                        } for user in users
                    ]
                })
                
            except Exception as e:
                logger.error(f"Get users API error: {e}")
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/api/test_recognition', methods=['GET'])
        def test_recognition():
            """Test endpoint to check if face recognition is working"""
            try:
                return jsonify({
                    "success": True,
                    "loaded_faces": len(self.known_names),
                    "names": self.known_names,
                    "message": "Face recognition system is operational"
                })
            except Exception as e:
                logger.error(f"Test recognition error: {e}")
                return jsonify({"success": False, "error": str(e)})
                
        @self.app.route('/api/suspicious_frame', methods=['POST'])
        def suspicious_frame():
            try:
                data = request.get_json()
                if not data or 'image' not in data:
                    return jsonify({"success": False, "error": "No image data provided"})
                
                if self.suspicious_pipeline is None:
                    from suspicious_pipeline import SuspiciousPipeline
                    self.suspicious_pipeline = SuspiciousPipeline()
                    
                result = self.suspicious_pipeline.process_frame_base64(data['image'])
                if result is None:
                    return jsonify({"success": False, "error": "Failed to process frame"})
                
                return jsonify({
                    "success": True,
                    "image": result["image"],
                    "active_alert": result["active_alert"]
                })
            except Exception as e:
                logger.error(f"Suspicious frame error: {e}")
                return jsonify({"success": False, "error": str(e)})

        @self.app.route('/api/suspicious_reset', methods=['POST'])
        def suspicious_reset():
            try:
                if self.suspicious_pipeline is not None:
                    self.suspicious_pipeline.reset()
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})

    def run(self, host='0.0.0.0', port=5000, debug=False, use_ssl=False):
        """Run the Flask application"""
        logger.info(f"Starting FaceGuard Pro server on {host}:{port}")
        
        if use_ssl and os.path.exists('cert.pem') and os.path.exists('key.pem'):
            logger.info("Running with SSL/HTTPS")
            self.app.run(host=host, port=port, debug=debug, ssl_context=('cert.pem', 'key.pem'))
        else:
            if use_ssl:
                logger.warning("SSL certificates not found. Running without SSL.")
                print("\n⚠️  To enable HTTPS, generate certificates:")
                print("openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365\n")
            self.app.run(host=host, port=port, debug=debug)


def main():
    """Main function to run the application"""
    print("="*60)
    print("🛡️  FaceGuard Pro - Advanced Face Recognition System")
    print("="*60)
    print("Initializing system...")
    
    try:
        face_system = FaceRecognitionSystem()
        
        print("\n✅ System initialized successfully!")
        print(f"📊 Loaded {len(face_system.known_names)} known faces")
        print(f"   Faces: {', '.join(face_system.known_names)}")
        print("\n🚀 Starting web server...")
        print("📱 Access the application:")
        print(f"   • Local: http://localhost:5000")
        print(f"   • Network: http://192.168.x.x:5000 (replace with your IP)")
        print("\n⚠️  CAMERA ACCESS REQUIREMENTS:")
        print("   • Use HTTPS or localhost for camera access")
        print("   • Grant camera permissions in browser")
        print("   • For network access, use ngrok or generate SSL certificates")
        print("\n💡 Features available:")
        print("   • Admin authentication (email/password)")
        print("   • Real-time face recognition")
        print("   • Attendance tracking")
        print("   • Emotion detection")
        print("   • Multi-user support")
        print("\n🔐 Admin Login:")
        print("   Email: kaushik29@gmail.com")
        print("   Password: kaushik123")
        print("\n" + "="*60)
        print("Press Ctrl+C to stop the server")
        print("="*60)
        
        face_system.run(debug=False)
        
    except KeyboardInterrupt:
        print("\n\n👋 FaceGuard Pro server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        logger.error(f"Server startup error: {e}")


if __name__ == "__main__":
    main()