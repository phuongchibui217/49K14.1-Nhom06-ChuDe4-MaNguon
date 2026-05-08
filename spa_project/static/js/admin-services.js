// Admin Services Page JavaScript

// ===== CHAR COUNTER FOR DESCRIPTION FIELDS =====
function updateCounter(inputId, counterId, maxLen) {
    const input = document.getElementById(inputId);
    const counter = document.getElementById(counterId);
    if (!input || !counter) return;
    const len = input.value.length;
    counter.textContent = `${len} / ${maxLen}`;
    counter.classList.remove('warn', 'over');
    if (len > maxLen) counter.classList.add('over');
    else if (len > maxLen * 0.85) counter.classList.add('warn');
}

function resetCounters() {
    updateCounter('shortDescInput', 'shortDescCounter', 255);
}

// ===== VARIANT MANAGEMENT =====

let variantCounter = 0;

function addVariantRow(data = {}) {
    const list = document.getElementById('variantList');
    if (!list) return;

    const id = ++variantCounter;
    const row = document.createElement('div');
    row.className = 'variant-row';
    row.dataset.variantId = id;
    row.innerHTML = `
        <div class="variant-label-row">
            <label>Tên gói</label>
            <input type="text" class="form-control form-control-sm" placeholder="VD: Gói cơ bản"
                   data-field="label" value="${escapeHtml(data.label || '')}">
        </div>
        <div class="variant-bottom-row">
            <div>
                <span class="sub-label">Thời lượng (phút)</span>
                <input type="number" class="form-control form-control-sm" placeholder="VD: 60"
                       data-field="duration_minutes" min="1" max="480" value="${data.duration_minutes || ''}" required>
            </div>
            <div>
                <span class="sub-label">Giá (VNĐ)</span>
                <input type="number" class="form-control form-control-sm" placeholder="VD: 200000"
                       data-field="price" min="0" step="1000" value="${data.price || ''}" required>
            </div>
            <button type="button" class="btn-remove-variant" onclick="removeVariantRow(this)" title="Xóa gói">
                <i class="fas fa-times"></i>
            </button>
        </div>`;
    list.appendChild(row);
}

function removeVariantRow(btn) {
    const row = btn.closest('.variant-row');
    if (row) row.remove();
}

function collectVariants() {
    const rows = document.querySelectorAll('#variantList .variant-row');
    const variants = [];
    let valid = true;

    if (rows.length === 0) {
        showToast('error', 'Vui lòng nhập đầy đủ thông tin gói');
        return null;
    }

    rows.forEach((row, i) => {
        const labelInput = row.querySelector('[data-field="label"]');
        const durationInput = row.querySelector('[data-field="duration_minutes"]');
        const priceInput = row.querySelector('[data-field="price"]');

        const labelVal = labelInput ? labelInput.value.trim() : '';
        const durationVal = durationInput ? durationInput.value.trim() : '';
        const priceVal = priceInput ? priceInput.value.trim() : '';

        if (durationVal === '' || priceVal === '') {
            showToast('error', 'Vui lòng nhập đầy đủ thông tin gói');
            valid = false; return;
        }

        const duration = parseInt(durationVal, 10);
        const price = parseFloat(priceVal);

        if (isNaN(duration) || duration <= 0) {
            showToast('error', 'Thời lượng không hợp lệ');
            valid = false; return;
        }
        if (isNaN(price) || price <= 0) {
            showToast('error', 'Giá dịch vụ không hợp lệ');
            valid = false; return;
        }

        const label = labelVal || `${duration} phút`;
        variants.push({ label, duration_minutes: duration, price });
    });
    return valid ? variants : null;
}

function clearVariantRows() {
    const list = document.getElementById('variantList');
    if (list) list.innerHTML = '';
    variantCounter = 0;
}

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ===== END VARIANT MANAGEMENT =====

// Track edit mode
let editingServiceId = null;
let existingImageUrl = null;

// ===== LOADING STATE HELPER =====
// Biến theo dõi trạng thái đang submit để tránh submit lặp
let isSubmitting = false;

/**
 * Bật loading state cho button
 * @param {HTMLElement} btn - Button cần set loading
 * @param {string} loadingText - Text hiển thị khi loading
 */
function setButtonLoading(btn, loadingText = 'Đang xử lý...') {
    if (!btn) return;
    
    // Lưu text gốc nếu chưa có
    if (!btn.dataset.originalText) {
        btn.dataset.originalText = btn.innerHTML;
    }
    
    btn.disabled = true;
    btn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>${loadingText}`;
}

/**
 * Tắt loading state và restore button về trạng thái ban đầu
 * @param {HTMLElement} btn - Button cần restore
 */
function resetButton(btn) {
    if (!btn) return;
    
    btn.disabled = false;
    if (btn.dataset.originalText) {
        btn.innerHTML = btn.dataset.originalText;
        delete btn.dataset.originalText;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    setupFilters();
    setupFormValidation();

    // Show Django messages as toast
    showDjangoMessagesAsToast();

    // Modal hidden event - reset form
    const addServiceModal = document.getElementById('addServiceModal');
    if (addServiceModal) {
        addServiceModal.addEventListener('hidden.bs.modal', function() {
            resetFormToAddMode();
        });
        // Khi mở modal ở chế độ thêm mới, đảm bảo có sẵn 1 dòng gói
        addServiceModal.addEventListener('show.bs.modal', function() {
            if (!isEditMode) {
                const list = document.getElementById('variantList');
                if (list && list.children.length === 0) {
                    addVariantRow();
                }
            }
        });
    }
});

// Setup Filters — UC 12.5
// Enter trên ô tìm kiếm = nhấn nút Lọc (3a/4a)
// Dropdown danh mục và trạng thái chỉ submit khi nhấn nút Lọc
function setupFilters() {
    const searchInput = document.getElementById('searchInput');
    const form = document.getElementById('searchFilterForm');

    if (!form) return;

    // Enter trên ô tìm kiếm → submit form (UC 3a / 4a)
    if (searchInput) {
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                form.submit();
            }
        });
    }
}

// Setup Form Validation
function setupFormValidation() {
    const form = document.getElementById('addServiceForm');
    if (!form) return;

    const nameInput = form.querySelector('[name="name"]');
    const categoryInput = form.querySelector('[name="category_number"]');
    const imageInput = form.querySelector('[name="image"]');

    if (nameInput) {
        nameInput.addEventListener('blur', function() {
            validateServiceName(this);
        });
    }

    if (categoryInput) {
        categoryInput.addEventListener('blur', function() {
            validateCategory(this);
        });
    }

    if (imageInput) {
        imageInput.addEventListener('change', function() {
            validateImage(this);
        });
    }
}

// Validation Functions
function validateServiceName(input) {
    const value = input.value.trim();

    clearFieldError(input);

    if (!value) {
        showFieldError(input, 'Tên dịch vụ không được để trống');
        return false;
    }

    if (value.length < 5) {
        showFieldError(input, 'Tên dịch vụ phải có ít nhất 5 ký tự');
        return false;
    }

    if (value.length > 200) {
        showFieldError(input, 'Tên dịch vụ không được quá 200 ký tự');
        return false;
    }

    if (value.match(/^\d+$/)) {
        showFieldError(input, 'Tên dịch vụ không hợp lệ');
        return false;
    }

    return true;
}

function validateCategory(input) {
    const value = input.value;

    clearFieldError(input);

    if (!value) {
        showFieldError(input, 'Vui lòng chọn danh mục');
        return false;
    }

    return true;
}

function validateImage(input) {
    const file = input.files[0];
    const previewDiv = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');

    clearFieldError(input);

    // Check if file exists or if editing (no new file)
    if (!file) {
        // For edit mode, allow no new image (will keep existing image)
        if (isEditMode) {
            // Show existing image if available
            if (existingImageUrl && previewDiv && previewImg) {
                previewImg.src = existingImageUrl;
                previewDiv.style.display = 'block';
            }
            return true;
        } else {
            // Require image when creating new service
            showFieldError(input, 'Vui lòng chọn hình ảnh dịch vụ');
            if (previewDiv) previewDiv.style.display = 'none';
            return false;
        }
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
        showFieldError(input, 'Hình ảnh không được quá 5MB');
        if (previewDiv) previewDiv.style.display = 'none';
        input.value = '';
        return false;
    }

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            showFieldError(input, 'Hình ảnh không đúng định dạng');
            if (previewDiv) previewDiv.style.display = 'none';
            input.value = '';
            return false;
        }

    return true;
}

function showFieldError(input, message) {
    const formGroup = input.closest('.mb-3, .col-md-4, .col-md-6');
    if (!formGroup) return;

    // Remove existing error
    const existingError = formGroup.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }

    // Add error class to input
    input.classList.add('is-invalid');

    // Add error message
    const errorDiv = document.createElement('div');
    errorDiv.className = 'field-error';
    errorDiv.textContent = message;
    formGroup.appendChild(errorDiv);
}

function clearFieldError(input) {
    input.classList.remove('is-invalid');

    const formGroup = input.closest('.mb-3, .col-md-4, .col-md-6');
    if (!formGroup) return;

    const errorMsg = formGroup.querySelector('.field-error');
    if (errorMsg) {
        errorMsg.remove();
    }
}

// Clear all field errors
function clearAllFieldErrors() {
    const fields = document.querySelectorAll('#addServiceForm .is-invalid');
    fields.forEach(field => {
        field.classList.remove('is-invalid');
    });

    const errorMessages = document.querySelectorAll('#addServiceForm .field-error');
    errorMessages.forEach(msg => msg.remove());
}

// Traditional Form Submit
function submitServiceForm(event) {
    event.preventDefault();

    // ===== NGĂN SUBMIT LẶP =====
    if (isSubmitting) {
        console.log('Đang xử lý, bỏ qua submit lặp');
        return false;
    }

    const form = document.getElementById('addServiceForm');
    if (!form) return false;

    // Validate all fields
    const nameInput = form.querySelector('[name="name"]');
    const categoryInput = form.querySelector('[name="category_number"]');
    const imageInput = form.querySelector('[name="image"]');
    const codeInput = form.querySelector('[name="code"]');
    const statusInput = form.querySelector('[name="status"]');

    let isValid = true;

    // Validate code
    if (codeInput && !codeInput.value.trim()) {
        showFieldError(codeInput, 'Vui lòng nhập mã dịch vụ');
        isValid = false;
    }

    // Validate category
    if (!validateCategory(categoryInput)) isValid = false;

    // Validate name
    if (!validateServiceName(nameInput)) isValid = false;

    // Validate status
    if (statusInput && !statusInput.value) {
        showFieldError(statusInput, 'Vui lòng chọn trạng thái dịch vụ');
        isValid = false;
    }

    // Validate image
    if (!validateImage(imageInput)) isValid = false;

    if (!isValid) {
        showToast('error', 'Vui lòng kiểm tra lại các thông tin!');
        return false;
    }

    // Validate variants (phải có ít nhất 1 gói)
    const variants = collectVariants();
    if (variants === null) return false;

    // ===== BẬT LOADING STATE =====
    isSubmitting = true;
    const submitBtn = document.querySelector('#addServiceModal .modal-footer .btn-primary');
    const loadingText = isEditMode ? 'Đang cập nhật...' : 'Đang thêm...';
    setButtonLoading(submitBtn, loadingText);

    // Create FormData for AJAX submission
    const formData = new FormData(form);
    formData.set('variants_json', JSON.stringify(variants));

    // Determine URL based on mode
    const url = isEditMode ? `/api/services/${editingServiceId}/update/` : '/api/services/create/';

    // Submit via AJAX
    fetch(url, {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('success', data.message);
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('addServiceModal'));
            if (modal) {
                modal.hide();
            }
            // Reload page after success
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        } else {
            showToast('error', data.error || 'Có lỗi khi lưu dữ liệu, vui lòng thử lại');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('error', 'Có lỗi khi lưu dữ liệu, vui lòng thử lại');
    })
    .finally(() => {
        // ===== TẮT LOADING STATE =====
        isSubmitting = false;
        resetButton(submitBtn);
    });

    return false;
}

// Preview Image
function previewImage(input) {
    const preview = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');

    if (input.files && input.files[0]) {
        const file = input.files[0];

        // Quick validation
        if (file.size > 5 * 1024 * 1024) {
            showToast('error', 'Hình ảnh không được quá 5MB!');
            input.value = '';
            if (preview) preview.style.display = 'none';
            return;
        }

        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            showToast('error', 'Chỉ chấp nhận file ảnh (JPG, PNG, WebP)!');
            input.value = '';
            if (preview) preview.style.display = 'none';
            return;
        }

        const reader = new FileReader();
        reader.onload = function(e) {
            if (previewImg) previewImg.src = e.target.result;
            if (preview) preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    } else {
        // If no file selected and in edit mode, show existing image
        if (isEditMode && existingImageUrl) {
            if (previewImg) previewImg.src = existingImageUrl;
            if (preview) preview.style.display = 'block';
        } else {
            if (preview) preview.style.display = 'none';
        }
    }
}

// Clear Image Preview
function clearImagePreview() {
    const preview = document.getElementById('imagePreview');
    const imageInput = document.querySelector('[name="image"]');

    if (imageInput) {
        imageInput.value = '';
    }

    if (preview) {
        preview.style.display = 'none';
    }
}

// Edit Service (opens modal and pre-fills data via AJAX)
function editService(serviceId) {
    // Reset edit mode first
    isEditMode = false;
    editingServiceId = null;
    existingImageUrl = null;

    // Fetch service data by ID
    fetch(`/api/services/?id=${serviceId}`)
        .then(response => response.json())
        .then(data => {
            const service = (data.services || [])[0];

            if (!service) {
                showToast('error', 'Không tìm thấy dịch vụ!');
                return;
            }

            // Set edit mode
            isEditMode = true;
            editingServiceId = serviceId;
            existingImageUrl = service.image || null;

            // Fill form
            const form = document.getElementById('addServiceForm');

            // Mã dịch vụ — editable khi sửa
            const codeInput = form.querySelector('[name="code"]');
            if (codeInput) {
                codeInput.value = service.code || '';
                codeInput.readOnly = false;
            }

            // Category — dùng categoryCode trực tiếp
            const catSelect = form.querySelector('[name="category_number"]');
            if (catSelect) {
                catSelect.value = service.categoryCode || '';
            }

            form.querySelector('[name="name"]').value = service.name || '';

            // Mô tả ngắn (trang danh sách)
            const shortDescField = form.querySelector('[name="short_description"]');
            if (shortDescField) {
                shortDescField.value = service.short_description || '';
                updateCounter('shortDescInput', 'shortDescCounter', 255);
            }

            // Mô tả chi tiết (trang chi tiết)
            const descField = form.querySelector('[name="description"]');
            if (descField) descField.value = service.detail_description || '';

            form.querySelector('[name="status"]').value = (service.status || 'ACTIVE').toUpperCase() === 'ACTIVE' ? 'ACTIVE' : 'INACTIVE';

            // Show existing image preview
            const previewDiv = document.getElementById('imagePreview');
            const previewImg = document.getElementById('previewImg');
            if (existingImageUrl && previewDiv && previewImg) {
                previewImg.src = existingImageUrl;
                previewDiv.style.display = 'block';
            } else if (previewDiv) {
                previewDiv.style.display = 'none';
            }

            // Load variants
            clearVariantRows();
            (service.variants || []).forEach(v => addVariantRow({
                label: v.label,
                duration_minutes: v.duration_minutes,
                price: v.price,
            }));

            // Make image not required in edit mode
            const imageInput = form.querySelector('[name="image"]');
            if (imageInput) {
                imageInput.removeAttribute('required');
            }

            // Change modal title and button
            const modalTitle = document.querySelector('#addServiceModal .modal-title');
            modalTitle.innerHTML = `<i class="fas fa-edit" style="color: #d4a853; margin-right: 0.5rem;"></i> Chỉnh sửa dịch vụ`;

            const modalFooter = document.querySelector('#addServiceModal .modal-footer .btn-primary');
            modalFooter.innerHTML = `<i class="fas fa-save me-2"></i> Cập nhật`;

            // Clear all errors
            clearAllFieldErrors();

            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('addServiceModal'));
            modal.show();
        })
        .catch(error => {
            console.error('Error loading service:', error);
            showToast('error', 'Không thể tải thông tin dịch vụ!');
        });
}

// Delete Service
function deleteService(serviceId) {
    // ===== NGĂN XÓA LẶP =====
    if (isSubmitting) {
        console.log('Đang xử lý, bỏ qua click lặp');
        return;
    }

    // ===== MỞ MODAL XÁC NHẬN =====
    const deleteModal = new bootstrap.Modal(document.getElementById('deleteServiceModal'));
    const confirmDeleteBtn = document.getElementById('confirmDeleteServiceBtn');

    // Lưu serviceId vào dataset của modal để sử dụng sau
    document.getElementById('deleteServiceModal').dataset.serviceId = serviceId;

    // Xử lý nút Xóa trong modal
    if (confirmDeleteBtn) {
        // Xóa event listener cũ (nếu có) để tránh trùng lặp
        const newBtn = confirmDeleteBtn.cloneNode(true);
        confirmDeleteBtn.parentNode.replaceChild(newBtn, confirmDeleteBtn);

        // Thêm event listener mới
        newBtn.addEventListener('click', function() {
            const modalServiceId = document.getElementById('deleteServiceModal').dataset.serviceId;

            // Đóng modal
            deleteModal.hide();

            // ===== BẬT LOADING STATE =====
            isSubmitting = true;
            showToast('warning', 'Đang xóa dịch vụ...');

            // Submit delete via API
            const csrfToken = getCookie('csrftoken');

            fetch(`/api/services/${modalServiceId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast('success', data.message);
                    // Reload page after success
                    setTimeout(() => {
                        window.location.reload();
                    }, 1000);
                } else {
                    showToast('error', data.error || 'Có lỗi xảy ra, vui lòng thử lại');
                    isSubmitting = false; // Reset khi lỗi
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('error', 'Có lỗi xảy ra, vui lòng thử lại');
                isSubmitting = false; // Reset khi lỗi
            });
        });

        // Cập nhật reference
    }

    // Mở modal
    deleteModal.show();
}

// Show Toast
function showToast(type, message) {
    const toast = document.getElementById('toast');
    const titleEl = document.getElementById('toastTitle');
    const bodyEl = document.getElementById('toastMessage');

    if (!toast) return;

    // Remove all existing classes
    toast.className = 'toast show ' + type;

    titleEl.textContent = type === 'success' ? 'Thành công' : type === 'warning' ? 'Đang xử lý...' : 'Lỗi';

    const icon = type === 'success' ? 'fa-check-circle' : type === 'warning' ? 'fa-spinner fa-spin' : 'fa-exclamation-circle';
    bodyEl.innerHTML = `<i class="fas ${icon}"></i> ${message}`;

    // Auto hide after 3 seconds for success, 5 seconds for others
    const hideTime = type === 'success' ? 3000 : 5000;
    setTimeout(function() {
        hideToast();
    }, hideTime);
}

// Hide Toast
function hideToast() {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.classList.remove('show');
    }
}

// Show Django Messages as Toast
function showDjangoMessagesAsToast() {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    // Find Django message toasts
    const djangoToasts = toastContainer.querySelectorAll('.toast:not(#toast)');
    djangoToasts.forEach(toast => {
        const isShow = toast.classList.contains('show');
        if (isShow) {
            const type = toast.classList.contains('success') ? 'success' :
                      toast.classList.contains('error') ? 'error' :
                      toast.classList.contains('warning') ? 'warning' : 'success';

            const titleEl = toast.querySelector('.toast-title');
            const bodyEl = toast.querySelector('.toast-body');

            if (titleEl && bodyEl) {
                const message = bodyEl.textContent || bodyEl.innerText;

                // Re-show as our custom toast
                setTimeout(() => {
                    showToast(type, message);
                }, 500);

                // Hide Django toast
                toast.classList.remove('show');
            }
        }
    });
}

// Get CSRF Token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Close Modal helper
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const modalInstance = bootstrap.Modal.getInstance(modal);
        if (modalInstance) {
            modalInstance.hide();
        }
    }
}

// Reset form to add mode
function resetFormToAddMode() {
    const form = document.getElementById('addServiceForm');
    if (!form) return;

    // Reset edit mode flags
    isEditMode = false;
    editingServiceId = null;
    existingImageUrl = null;

    // Reset form
    form.reset();

    // Reset char counters
    resetCounters();

    // Reset modal title and button
    const modalTitle = document.querySelector('#addServiceModal .modal-title');
    if (modalTitle) {
        modalTitle.innerHTML = `<i class="fas fa-plus" style="color: #d4a853; margin-right: 0.5rem;"></i> Thêm dịch vụ mới`;
    }

    const modalFooter = document.querySelector('#addServiceModal .modal-footer .btn-primary');
    if (modalFooter) {
        modalFooter.innerHTML = `<i class="fas fa-plus me-2"></i> Thêm dịch vụ`;
        modalFooter.disabled = false;
    }

    // Make image required again
    const imageInput = form.querySelector('[name="image"]');
    if (imageInput) {
        imageInput.setAttribute('required', 'required');
    }

    // Clear image preview
    clearImagePreview();

    // Clear variant rows, then add 1 default row
    clearVariantRows();
    addVariantRow();

    // Clear all errors
    clearAllFieldErrors();

    // Reset readonly fields
    const codeInput = form.querySelector('[name="code"]');
    if (codeInput) {
        codeInput.readOnly = false;
    }
}