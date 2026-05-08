// ============================================
// Spa ANA - JavaScript (No Auth Logic)
// Auth handled by Django backend
// ============================================

document.addEventListener('DOMContentLoaded', function() {

    // ============================================
    // Initialize Bootstrap Components
    // ============================================

    // Initialize all tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    })

    // Initialize dropdowns
    var dropdownElementList = [].slice.call(document.querySelectorAll('[data-bs-toggle="dropdown"]'))
    var dropdownList = dropdownElementList.map(function (dropdownToggleEl) {
        return new bootstrap.Dropdown(dropdownToggleEl)
    })

    // ============================================
    // Navbar Scroll Effect
    // ============================================

    const navbar = document.querySelector('.navbar');

    if (navbar) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 50) {
                navbar.classList.add('shadow');
                navbar.style.padding = '0.5rem 0';
            } else {
                navbar.classList.remove('shadow');
                navbar.style.padding = '1rem 0';
            }
        });
    }

    // ============================================
    // Active Navigation Link (Template handles this with request.resolver_match)
    // ============================================

    // ============================================
    // Smooth Scroll for Anchor Links
    // ============================================

    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href === '#' || href.length === 1) return; // Skip empty anchors

            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // ============================================
    // FORM VALIDATION HELPERS (UX only, validation is backend)
    // ============================================

    function showFieldError(fieldId, message) {
        const field = document.getElementById(fieldId);
        if (field) {
            let errorDiv = field.nextElementSibling;
            if (!errorDiv || !errorDiv.classList.contains('field-error')) {
                errorDiv = document.createElement('div');
                errorDiv.className = 'field-error text-danger small mt-1';
                field.parentNode.insertBefore(errorDiv, field.nextSibling);
            }
            errorDiv.innerHTML = `<i class="fas fa-exclamation-circle me-1"></i>${message}`;
            field.classList.add('is-invalid');
            field.classList.add('border-danger');
        }
    }

    function clearFieldError(fieldId) {
        const field = document.getElementById(fieldId);
        if (field) {
            let errorDiv = field.nextElementSibling;
            if (errorDiv && errorDiv.classList.contains('field-error')) {
                errorDiv.remove();
            }
            field.classList.remove('is-invalid');
            field.classList.remove('border-danger');
        }
    }

    // Phone validation helper
    function validatePhone(phone) {
        const re = /(84|0[3|5|7|8|9])+([0-9]{8})\b/;
        return re.test(phone);
    }

    // Email validation helper
    function validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    // ============================================
    // ALERT & LOADING FUNCTIONS
    // ============================================

    function showAlert(type, message) {
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.custom-alert');
        existingAlerts.forEach(alert => alert.remove());

        const alertDiv = document.createElement('div');
        alertDiv.className = `custom-alert alert alert-${type} alert-dismissible fade show`;
        alertDiv.setAttribute('role', 'alert');
        alertDiv.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            animation: fadeInUp 0.3s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border-radius: 8px;
        `;

        const icon = type === 'success' ? '<i class="fas fa-check-circle me-2"></i>' :
                    type === 'error' ? '<i class="fas fa-exclamation-circle me-2"></i>' :
                    '<i class="fas fa-info-circle me-2"></i>';

        alertDiv.innerHTML = `
            ${icon}${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alertDiv);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (alertDiv) {
                alertDiv.remove();
            }
        }, 5000);
    }

    function showLoading() {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'loadingOverlay';
        loadingDiv.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255,255,255,0.9);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;

        loadingDiv.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-warning" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3 text-muted fw-bold">Đang xử lý...</p>
            </div>
        `;

        document.body.appendChild(loadingDiv);
    }

    function hideLoading() {
        const loadingDiv = document.getElementById('loadingOverlay');
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }

    // ============================================
    // PASSWORD STRENGTH INDICATOR (Register form)
    // ============================================

    const password1Input = document.getElementById('id_password1');
    const passwordStrength = document.getElementById('passwordStrength');

    if (password1Input && passwordStrength) {
        password1Input.addEventListener('input', function() {
            const password = this.value;
            let strength = 0;

            if (password.length >= 6) strength++;
            if (password.length >= 8) strength++;
            if (/[A-Z]/.test(password)) strength++;
            if (/[0-9]/.test(password)) strength++;
            if (/[^A-Za-z0-9]/.test(password)) strength++;

            passwordStrength.className = 'password-strength';
            if (password.length === 0) {
                passwordStrength.style.width = '0%';
            } else if (strength <= 2) {
                passwordStrength.classList.add('weak');
            } else if (strength <= 3) {
                passwordStrength.classList.add('medium');
            } else {
                passwordStrength.classList.add('strong');
            }
        });
    }

    // Password match validation
    const password2Input = document.getElementById('id_password2');
    if (password2Input && password1Input) {
        password2Input.addEventListener('input', function() {
            if (this.value && this.value !== password1Input.value) {
                this.setCustomValidity('Mật khẩu không khớp');
            } else {
                this.setCustomValidity('');
            }
        });
    }

    // ============================================
    // SCROLL TO TOP BUTTON
    // ============================================

    const scrollBtn = document.createElement('button');
    scrollBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    scrollBtn.className = 'scroll-top-btn';
    scrollBtn.style.cssText = `
        position: fixed;
        bottom: 30px;
        right: 30px;
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background: #c9a96e;
        color: white;
        border: none;
        cursor: pointer;
        display: none;
        z-index: 999;
        box-shadow: 0 4px 12px rgba(201,169,110,.35);
        transition: all 0.2s ease;
        font-size: 1rem;
    `;

    document.body.appendChild(scrollBtn);

    window.addEventListener('scroll', function() {
        if (window.scrollY > 300) {
            scrollBtn.style.display = 'block';
        } else {
            scrollBtn.style.display = 'none';
        }
    });

    scrollBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    // ============================================
    // SERVICE FILTER (Services page)
    // ============================================

    window.filterServices = function(category) {
        const items = document.querySelectorAll('.service-item');
        const buttons = document.querySelectorAll('[onclick^="filterServices"]');

        // Update button styles
        buttons.forEach(btn => {
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-outline-warning');
        });

        // Find and activate the clicked button
        event.target.classList.remove('btn-outline-warning');
        event.target.classList.add('btn-warning');

        // Filter items
        items.forEach(item => {
            if (category === 'all' || item.dataset.category === category) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    };

    // ============================================
    // COMPLAINT FORM (Real submit to backend)
    // ============================================

    const complaintForm = document.querySelector('form[action*="complaint"]');
    if (complaintForm) {
        const phoneInput = complaintForm.querySelector('input[name="phone"]');
        const emailInput = complaintForm.querySelector('input[name="email"]');

        if (phoneInput) {
            phoneInput.addEventListener('blur', function() {
                clearFieldError('phone');
                if (this.value && !validatePhone(this.value)) {
                    showFieldError('phone', 'Số điện thoại không hợp lệ!');
                }
            });
        }

        if (emailInput) {
            emailInput.addEventListener('blur', function() {
                clearFieldError('email');
                if (this.value && !validateEmail(this.value)) {
                    showFieldError('email', 'Email không hợp lệ!');
                }
            });
        }
    }

    // ============================================
    // BOOKING FORM (Real submit to backend)
    // ============================================

    const bookingForm = document.querySelector('form[action*="booking"]');
    if (bookingForm) {
        const dateInput = bookingForm.querySelector('input[name="appointment_date"]');

        // Set min date to today (dùng local date, không dùng toISOString() vì trả về UTC)
        if (dateInput) {
            const _n = new Date();
            const today = `${_n.getFullYear()}-${String(_n.getMonth()+1).padStart(2,'0')}-${String(_n.getDate()).padStart(2,'0')}`;
            dateInput.setAttribute('min', today);
        }
    }

    // ============================================
    // LOG - Loaded successfully
    // ============================================

    console.log('Spa ANA Website loaded successfully!');
    console.log('✓ Auth handled by Django backend');
    console.log('✓ Forms submit to server with validation');
    console.log('✓ Client-side validation for UX only');
});
