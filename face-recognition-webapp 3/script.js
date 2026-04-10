// FaceGuard Pro - Enhanced JavaScript with Premium Features

class FaceGuardPro {
    constructor() {
        this.currentPage = 'welcomePage';
        this.video = null;
        this.canvas = null;
        this.ctx = null;
        this.stream = null;
        this.isRecognizing = false;
        this.recognition_interval = null;
        this.suspicious_interval = null;
        this.isSuspiciousMode = false;
        this.adminSessionToken = null;
        this.isAdminLoggedIn = false;
        this.deferredPrompt = null;
        
        this.init();
    }

    init() {
        this.checkAdminSession();
        this.setupEventListeners();
        this.initTheme();
        this.setupPWA();
        this.createParticles();
        this.initCardTilt();
        
        console.log('🛡️ FaceGuard Pro initialized successfully');
    }

    // Particle System
    createParticles() {
        const particlesContainer = document.getElementById('particles');
        if (!particlesContainer) return;

        for (let i = 0; i < 50; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            particle.style.cssText = `
                position: absolute;
                width: 2px;
                height: 2px;
                background: rgba(102, 126, 234, 0.5);
                border-radius: 50%;
                left: ${Math.random() * 100}%;
                top: ${Math.random() * 100}%;
                animation: particleFloat ${10 + Math.random() * 20}s linear infinite;
                animation-delay: ${Math.random() * 5}s;
            `;
            particlesContainer.appendChild(particle);
        }

        // Add particle animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes particleFloat {
                0% { transform: translateY(0) translateX(0); opacity: 0; }
                10% { opacity: 1; }
                90% { opacity: 1; }
                100% { transform: translateY(-100vh) translateX(${Math.random() * 100 - 50}px); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }

    // Card Tilt Effect
    initCardTilt() {
        const cards = document.querySelectorAll('[data-tilt]');
        cards.forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                
                const rotateX = (y - centerY) / 10;
                const rotateY = (centerX - x) / 10;
                
                card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-15px)`;
            });
            
            card.addEventListener('mouseleave', () => {
                card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateY(0)';
            });
        });
    }

    // Admin Session Management
    checkAdminSession() {
        const sessionToken = localStorage.getItem('adminSessionToken');
        if (sessionToken) {
            this.verifyAdminSession(sessionToken);
        }
    }

    async verifyAdminSession(sessionToken) {
        try {
            const response = await fetch('/api/admin/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_token: sessionToken })
            });

            const result = await response.json();
            
            if (result.success) {
                this.adminSessionToken = sessionToken;
                this.isAdminLoggedIn = true;
                this.updateAdminUI(true);
            } else {
                localStorage.removeItem('adminSessionToken');
                this.isAdminLoggedIn = false;
                this.updateAdminUI(false);
            }
        } catch (error) {
            console.error('Session verification error:', error);
            this.isAdminLoggedIn = false;
            this.updateAdminUI(false);
        }
    }

    updateAdminUI(isLoggedIn) {
        const loginBtn = document.getElementById('adminLoginBtn');
        const logoutBtn = document.getElementById('adminLogoutBtn');
        
        if (isLoggedIn) {
            loginBtn && (loginBtn.style.display = 'none');
            logoutBtn && (logoutBtn.style.display = 'flex');
        } else {
            loginBtn && (loginBtn.style.display = 'flex');
            logoutBtn && (logoutBtn.style.display = 'none');
        }
    }

    showAdminLoginModal() {
        const modal = document.getElementById('adminLoginModal');
        modal && modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    hideAdminLoginModal() {
        const modal = document.getElementById('adminLoginModal');
        if (modal) {
            modal.classList.remove('active');
            document.getElementById('adminEmail').value = '';
            document.getElementById('adminPassword').value = '';
            const errorDiv = document.getElementById('loginError');
            errorDiv && (errorDiv.style.display = 'none');
        }
        document.body.style.overflow = '';
    }

    async adminLogin() {
        const email = document.getElementById('adminEmail').value.trim();
        const password = document.getElementById('adminPassword').value;
        const errorDiv = document.getElementById('loginError');

        if (!email || !password) {
            errorDiv.textContent = '⚠️ Please enter both email and password';
            errorDiv.style.display = 'block';
            return;
        }

        try {
            this.showLoading(true);
            errorDiv.style.display = 'none';

            const response = await fetch('/api/admin/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const result = await response.json();

            if (result.success) {
                this.adminSessionToken = result.session_token;
                this.isAdminLoggedIn = true;
                localStorage.setItem('adminSessionToken', result.session_token);
                
                this.hideAdminLoginModal();
                this.updateAdminUI(true);
                this.showNotification(`🎉 Welcome back, ${result.admin_name}!`, 'success');
            } else {
                errorDiv.textContent = `❌ ${result.error || 'Login failed'}`;
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Login error:', error);
            errorDiv.textContent = '❌ Network error. Please try again.';
            errorDiv.style.display = 'block';
        }

        this.showLoading(false);
    }

    async adminLogout() {
        try {
            this.showLoading(true);

            await fetch('/api/admin/logout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_token: this.adminSessionToken })
            });

            this.adminSessionToken = null;
            this.isAdminLoggedIn = false;
            localStorage.removeItem('adminSessionToken');
            this.updateAdminUI(false);
            
            this.showNotification('👋 Logged out successfully', 'success');
        } catch (error) {
            console.error('Logout error:', error);
        }

        this.showLoading(false);
    }

    // Event Listeners Setup
    setupEventListeners() {
        // Navigation
        document.getElementById('startRecognition')?.addEventListener('click', () => {
            this.isSuspiciousMode = false;
            document.getElementById('scanOverlay').style.display = 'block';
            document.getElementById('video').style.opacity = '1';
            document.getElementById('suspiciousResultImg').style.display = 'none';
            document.getElementById('captureBtn').style.display = 'flex';
            document.getElementById('stopSuspiciousBtn').style.display = 'none';
            document.querySelector('.camera-title span').textContent = 'Biometric Scanner';
            document.querySelector('.camera-subtitle').textContent = 'Position your face within the frame for instant recognition';
            this.showPage('cameraPage');
            this.initCamera();
        });

        document.getElementById('startSuspiciousAI')?.addEventListener('click', () => {
            this.isSuspiciousMode = true;
            document.getElementById('scanOverlay').style.display = 'none';
            document.getElementById('video').style.opacity = '0';
            document.getElementById('suspiciousResultImg').style.display = 'block';
            document.getElementById('captureBtn').style.display = 'none';
            document.getElementById('stopSuspiciousBtn').style.display = 'flex';
            document.querySelector('.camera-title span').textContent = 'Threat Monitoring';
            document.querySelector('.camera-subtitle').textContent = 'Active surveillance and behavior analysis pipeline';
            
            // notify backend to reset state
            fetch('/api/suspicious_reset', { method: 'POST' }).catch(console.error);

            this.showPage('cameraPage');
            this.initCamera();
        });

        document.getElementById('stopSuspiciousBtn')?.addEventListener('click', () => {
            this.stopCamera();
            this.showPage('welcomePage');
        });

        document.getElementById('backBtn')?.addEventListener('click', () => {
            this.stopCamera();
            this.showPage('welcomePage');
        });

        document.getElementById('captureBtn')?.addEventListener('click', () => {
            this.captureAndRecognize();
        });

        document.getElementById('recognizeAgain')?.addEventListener('click', () => {
            this.showPage('cameraPage');
            this.initCamera();
        });

        document.getElementById('homeBtn')?.addEventListener('click', () => {
            this.showPage('welcomePage');
        });

        // Admin controls
        document.getElementById('adminLoginBtn')?.addEventListener('click', () => {
            this.showAdminLoginModal();
        });

        document.getElementById('adminLogoutBtn')?.addEventListener('click', () => {
            this.adminLogout();
        });

        document.getElementById('loginSubmitBtn')?.addEventListener('click', () => {
            this.adminLogin();
        });

        document.getElementById('closeLoginModal')?.addEventListener('click', () => {
            this.hideAdminLoginModal();
        });

        document.getElementById('closeLoginModal2')?.addEventListener('click', () => {
            this.hideAdminLoginModal();
        });

        // Enter key for login
        document.getElementById('adminPassword')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.adminLogin();
        });

        // Theme toggle
        document.getElementById('themeToggle')?.addEventListener('click', () => {
            this.toggleTheme();
        });

        // Attendance modal
        document.getElementById('viewAttendance')?.addEventListener('click', () => {
            this.showAttendanceModal();
        });

        document.getElementById('closeModal')?.addEventListener('click', () => {
            this.hideAttendanceModal();
        });

        // PWA install
        document.getElementById('installBtn')?.addEventListener('click', () => {
            this.installPWA();
        });

        // Modal backdrop clicks
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal || e.target.classList.contains('modal-backdrop')) {
                    if (modal.id === 'adminLoginModal') {
                        this.hideAdminLoginModal();
                    } else if (modal.id === 'attendanceModal') {
                        this.hideAttendanceModal();
                    }
                }
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideAttendanceModal();
                this.hideAdminLoginModal();
            }
            if (e.key === ' ' && this.currentPage === 'cameraPage') {
                e.preventDefault();
                this.captureAndRecognize();
            }
        });
    }

    // Page Navigation
    showPage(pageId) {
        document.querySelectorAll('.page').forEach(page => {
            page.classList.remove('active');
        });
        
        document.getElementById(pageId)?.classList.add('active');
        this.currentPage = pageId;
        
        if (pageId === 'successPage') {
            this.triggerSuccessAnimations();
        }
    }

    // Camera Functions
    async initCamera() {
        try {
            this.showStatus('🔄 Initializing Camera...', 'scanning');
            
            if (!navigator.mediaDevices?.getUserMedia) {
                throw new Error('Camera not supported in this browser');
            }
            
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user'
                }
            });

            this.video = document.getElementById('video');
            this.canvas = document.getElementById('canvas');
            this.ctx = this.canvas?.getContext('2d');

            if (!this.video) {
                throw new Error('Video element not found');
            }

            this.video.srcObject = this.stream;
            
            this.video.addEventListener('loadedmetadata', () => {
                if (this.canvas) {
                    this.canvas.width = this.video.videoWidth;
                    this.canvas.height = this.video.videoHeight;
                }
                
                if (this.isSuspiciousMode) {
                    this.showStatus('🟢 Threat Monitoring Active', 'recognized');
                    this.startSuspiciousDetection();
                } else {
                    this.showStatus('✅ Camera Ready - Position your face', 'scanning');
                    this.startFaceDetection();
                }
            });

        } catch (error) {
            console.error('Camera error:', error);
            this.showStatus('❌ Camera Error', 'error');
            this.showNotification(`Camera Error: ${error.message}\n\nPlease ensure:\n• Camera is connected\n• Permissions are granted\n• Using HTTPS or localhost`, 'error');
        }
    }

    startFaceDetection() {
        this.recognition_interval = setInterval(() => {
            if (!this.isRecognizing) {
                this.showStatus('👤 Face Detected - Ready to scan', 'scanning');
            }
        }, 100);
    }

    startSuspiciousDetection() {
        let isProcessing = false;
        const resultImg = document.getElementById('suspiciousResultImg');
        const alertAudio = document.getElementById('alertSound');
        
        this.suspicious_interval = setInterval(async () => {
            if (isProcessing || !this.isSuspiciousMode) return;
            
            isProcessing = true;
            try {
                this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
                const imageData = this.canvas.toDataURL('image/jpeg', 0.6); // slight compression for speed

                const response = await fetch('/api/suspicious_frame', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image: imageData.split(',')[1] })
                });

                if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        resultImg.src = 'data:image/jpeg;base64,' + result.image;
                        
                        if (result.active_alert !== "NONE") {
                            this.showStatus('⚠️ ' + result.active_alert, 'error');
                            resultImg.style.boxShadow = '0 0 30px rgba(255, 0, 0, 0.7)';
                            if (alertAudio && alertAudio.paused) {
                                alertAudio.play().catch(e => console.log('Audio play failed: ', e));
                            }
                        } else {
                            this.showStatus('🟢 Monitoring Space...', 'recognized');
                            resultImg.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
                        }
                    }
                }
            } catch (err) {
                console.error("Suspicious detection error:", err);
            }
            isProcessing = false;
        }, 150); // ~7-10 fps depending on processing
    }

    async captureAndRecognize() {
        if (this.isRecognizing) return;
        
        this.isRecognizing = true;
        this.showLoading(true);
        this.showStatus('🔍 Processing Recognition...', 'scanning');

        try {
            this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
            const imageData = this.canvas.toDataURL('image/jpeg', 0.8);

            const response = await fetch('/api/recognize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: imageData.split(',')[1] })
            });

            if (!response.ok) {
                throw new Error('Recognition request failed');
            }

            const result = await response.json();
            
            if (result.success && result.name !== 'Unknown') {
                this.showStatus(`✅ Recognized: ${result.name}`, 'recognized');
                
                setTimeout(() => {
                    this.showSuccessPage(result);
                }, 1500);
            } else {
                this.showStatus('❌ Person not recognized', 'error');
                this.showUnknownPersonDialog();
            }

        } catch (error) {
            console.error('Recognition error:', error);
            this.showStatus('❌ Recognition failed', 'error');
            this.showNotification('Recognition failed. Please try again.', 'error');
        }

        this.showLoading(false);
        this.isRecognizing = false;
    }

    showSuccessPage(result) {
        this.stopCamera();
        
        document.getElementById('userName').textContent = `Welcome back, ${result.name}!`;
        document.getElementById('loginTime').textContent = new Date().toLocaleTimeString();
        document.getElementById('loginDate').textContent = new Date().toLocaleDateString();
        document.getElementById('userMood').textContent = result.emotion || 'Happy';
        document.getElementById('confidence').textContent = `${Math.round(result.confidence * 100)}%`;
        
        this.updateMotivationalQuote();
        this.showPage('successPage');
        this.playVoiceGreeting(result.name);
    }

    updateMotivationalQuote() {
        const quotes = [
            { text: "The future belongs to those who believe in the beauty of their dreams.", author: "Eleanor Roosevelt" },
            { text: "Success is not final, failure is not fatal: it is the courage to continue that counts.", author: "Winston Churchill" },
            { text: "The only way to do great work is to love what you do.", author: "Steve Jobs" },
            { text: "Innovation distinguishes between a leader and a follower.", author: "Steve Jobs" },
            { text: "Your future is created by what you do today, not tomorrow.", author: "Robert Kiyosaki" },
            { text: "The best time to plant a tree was 20 years ago. The second best time is now.", author: "Chinese Proverb" }
        ];
        
        const randomQuote = quotes[Math.floor(Math.random() * quotes.length)];
        document.getElementById('quoteText').textContent = randomQuote.text;
        document.getElementById('quoteAuthor').textContent = `- ${randomQuote.author}`;
    }

    triggerSuccessAnimations() {
        this.createConfetti();
        this.playSuccessSound();
    }

    createConfetti() {
        const container = document.getElementById('confettiContainer');
        if (!container) return;
        
        container.innerHTML = '';
        const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe'];
        
        for (let i = 0; i < 150; i++) {
            const confetti = document.createElement('div');
            confetti.className = 'confetti';
            confetti.style.left = Math.random() * 100 + '%';
            confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
            confetti.style.animationDelay = Math.random() * 2 + 's';
            confetti.style.animationDuration = (Math.random() * 3 + 2) + 's';
            container.appendChild(confetti);
        }
        
        setTimeout(() => { container.innerHTML = ''; }, 5000);
    }

    playVoiceGreeting(name) {
        try {
            if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(
                    `Welcome back ${name}! Hope you're having a great day.`
                );
                utterance.rate = 0.9;
                utterance.pitch = 1;
                utterance.volume = 0.7;
                speechSynthesis.speak(utterance);
            }
        } catch (error) {
            console.log('Voice greeting not available:', error);
        }
    }

    playSuccessSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.5);
        } catch (error) {
            console.log('Audio not available:', error);
        }
    }

    showUnknownPersonDialog() {
        if (!this.isAdminLoggedIn) {
            this.showNotification('⚠️ Person not recognized. Only administrators can add new people to the system.', 'warning');
            return;
        }

        const result = confirm('❓ Person not recognized. Would you like to add this person to the database?');
        if (result) {
            const name = prompt('Enter the person\'s name:');
            if (name) this.addNewPerson(name);
        }
    }

    async addNewPerson(name) {
        if (!this.isAdminLoggedIn) {
            this.showNotification('🔒 Only administrators can add new people.', 'error');
            return;
        }

        try {
            this.showLoading(true);
            const imageData = this.canvas.toDataURL('image/jpeg', 0.8);
            
            const response = await fetch('/api/add_person', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    image: imageData.split(',')[1],
                    session_token: this.adminSessionToken
                })
            });

            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`✅ ${name} has been added successfully!`, 'success');
                this.showSuccessPage({ name: name, confidence: 1.0, emotion: 'Happy' });
            } else {
                this.showNotification(`❌ Failed to add person: ${result.error}`, 'error');
            }
        } catch (error) {
            console.error('Add person error:', error);
            this.showNotification('❌ Failed to add person. Please try again.', 'error');
        }
        
        this.showLoading(false);
    }

    async showAttendanceModal() {
        try {
            const response = await fetch('/api/attendance');
            const data = await response.json();
            
            if (data.success) {
                document.getElementById('totalDays').textContent = data.total_days || 0;
                document.getElementById('avgTime').textContent = data.avg_time || '--:--';
                document.getElementById('streak').textContent = data.streak || 0;
                
                const attendanceList = document.getElementById('attendanceList');
                attendanceList.innerHTML = '';
                
                if (data.records && data.records.length > 0) {
                    data.records.forEach(record => {
                        const item = document.createElement('div');
                        item.className = 'attendance-item';
                        item.innerHTML = `
                            <div>
                                <div class="attendance-date">${record.name}</div>
                                <div class="attendance-time">${new Date(record.timestamp).toLocaleDateString()}</div>
                            </div>
                            <div class="attendance-time">
                                ${new Date(record.timestamp).toLocaleTimeString()}
                            </div>
                        `;
                        attendanceList.appendChild(item);
                    });
                } else {
                    attendanceList.innerHTML = '<div class="attendance-item">📊 No attendance records found</div>';
                }
                
                document.getElementById('attendanceModal').classList.add('active');
                document.body.style.overflow = 'hidden';
            }
        } catch (error) {
            console.error('Failed to fetch attendance:', error);
            this.showNotification('❌ Failed to load attendance data', 'error');
        }
    }

    hideAttendanceModal() {
        document.getElementById('attendanceModal')?.classList.remove('active');
        document.body.style.overflow = '';
    }

    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        
        if (this.recognition_interval) {
            clearInterval(this.recognition_interval);
            this.recognition_interval = null;
        }
        
        if (this.suspicious_interval) {
            clearInterval(this.suspicious_interval);
            this.suspicious_interval = null;
            
            // Turn off audio
            const alertAudio = document.getElementById('alertSound');
            if (alertAudio) {
                alertAudio.pause();
                alertAudio.currentTime = 0;
            }
            // reset API
            fetch('/api/suspicious_reset', { method: 'POST' }).catch(console.error);
        }
        
        if (this.video) {
            this.video.srcObject = null;
        }
    }

    showStatus(message, type = '') {
        const statusElement = document.getElementById('status');
        const statusText = statusElement?.querySelector('span');
        const statusDot = statusElement?.querySelector('.status-dot');
        
        if (statusText) statusText.textContent = message;
        
        if (statusDot) {
            if (type === 'recognized') {
                statusDot.style.background = '#4caf50';
            } else if (type === 'error') {
                statusDot.style.background = '#ff4444';
            } else {
                statusDot.style.background = 'var(--success)';
            }
        }
    }

    showLoading(show) {
        const spinner = document.getElementById('loadingSpinner');
        if (show) {
            spinner?.classList.add('active');
        } else {
            spinner?.classList.remove('active');
        }
    }

    showNotification(message, type = 'info') {
        alert(message);
    }

    // Theme Management
    initTheme() {
        const savedTheme = localStorage.getItem('faceGuardTheme') || 'dark';
        this.setTheme(savedTheme);
    }

    toggleTheme() {
        const currentTheme = document.body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    }

    setTheme(theme) {
        document.body.setAttribute('data-theme', theme);
        localStorage.setItem('faceGuardTheme', theme);
        
        const themeIcon = document.querySelector('#themeToggle i');
        if (themeIcon) {
            themeIcon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }
    }

    // PWA Support
    setupPWA() {
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            const installBtn = document.getElementById('installBtn');
            installBtn && (installBtn.style.display = 'flex');
        });

        window.addEventListener('appinstalled', () => {
            console.log('✅ FaceGuard Pro installed successfully');
            const installBtn = document.getElementById('installBtn');
            installBtn && (installBtn.style.display = 'none');
        });
    }

    async installPWA() {
        if (this.deferredPrompt) {
            this.deferredPrompt.prompt();
            const { outcome } = await this.deferredPrompt.userChoice;
            
            if (outcome === 'accepted') {
                console.log('✅ User accepted PWA installation');
            }
            
            this.deferredPrompt = null;
            const installBtn = document.getElementById('installBtn');
            installBtn && (installBtn.style.display = 'none');
        }
    }

    cleanup() {
        this.stopCamera();
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    window.faceGuardPro = new FaceGuardPro();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    window.faceGuardPro?.cleanup();
});