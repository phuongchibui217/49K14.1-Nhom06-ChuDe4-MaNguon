(function () {
  function ensureDialogModal() {
    var modalEl = document.getElementById('logoutConfirmModal');

    if (!modalEl) {
      var style = document.createElement('style');
      style.textContent = [
        '#logoutConfirmModal.modal{backdrop-filter:blur(3px);background:rgba(0,0,0,.35);}',
        '.modal-backdrop{backdrop-filter:blur(3px);}',
        '#logoutConfirmModal .modal-dialog{max-width:400px;width:92%;}',
        '#logoutConfirmModal .modal-content{border:none;border-radius:20px;box-shadow:0 24px 64px rgba(0,0,0,.14),0 4px 16px rgba(0,0,0,.08);padding:32px 28px 28px;text-align:center;background:#fff;animation:logoutModalIn .2s cubic-bezier(.34,1.2,.64,1);}',
        '@keyframes logoutModalIn{from{opacity:0;transform:scale(.96);}to{opacity:1;transform:scale(1);}}',
        '.logout-modal-icon{display:inline-flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:50%;border:2.5px solid #e53935;color:#e53935;font-size:22px;font-weight:700;margin-bottom:18px;line-height:1;flex-shrink:0;}',
        '.logout-modal-title{font-size:21px;font-weight:700;color:#111827;margin:0 0 10px;line-height:1.3;}',
        '.logout-modal-desc{font-size:15px;color:#6b7280;line-height:1.6;margin:0 0 28px;}',
        '.logout-modal-actions{display:flex;gap:14px;}',
        '.logout-modal-actions .btn-cancel,.logout-modal-actions .btn-logout-confirm{flex:1;height:50px;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;transition:background .18s,box-shadow .18s,transform .15s;}',
        '.logout-modal-actions .btn-cancel{background:#f3f4f6;color:#374151;}',
        '.logout-modal-actions .btn-cancel:hover{background:#e5e7eb;}',
        '.logout-modal-actions .btn-logout-confirm{background:#e53935;color:#fff;box-shadow:0 4px 14px rgba(229,57,53,.28);}',
        '.logout-modal-actions .btn-logout-confirm:hover{background:#c62828;box-shadow:0 6px 18px rgba(229,57,53,.38);transform:translateY(-1px);}'
      ].join('');
      document.head.appendChild(style);

      modalEl = document.createElement('div');
      modalEl.className = 'modal fade';
      modalEl.id = 'logoutConfirmModal';
      modalEl.tabIndex = -1;
      modalEl.setAttribute('aria-hidden', 'true');
      modalEl.innerHTML = [
        '<div class="modal-dialog modal-dialog-centered">',
        '  <div class="modal-content">',
        '    <div class="d-flex justify-content-center">',
        '      <div class="logout-modal-icon" aria-hidden="true">!</div>',
        '    </div>',
        '    <h5 class="logout-modal-title" id="logoutConfirmModalLabel"></h5>',
        '    <p class="logout-modal-desc"></p>',
        '    <div class="logout-modal-actions">',
        '      <button type="button" class="btn-cancel" data-bs-dismiss="modal">Hủy</button>',
        '      <button type="button" class="btn-logout-confirm" id="confirmLogoutBtn">Xác nhận</button>',
        '    </div>',
        '  </div>',
        '</div>'
      ].join('');
      document.body.appendChild(modalEl);
    }

    return modalEl;
  }

  function replaceButton(button) {
    var fresh = button.cloneNode(true);
    button.parentNode.replaceChild(fresh, button);
    return fresh;
  }

  function removePromptField(modalEl) {
    var existing = modalEl.querySelector('.logout-modal-prompt-wrap');
    if (existing) existing.remove();
  }

  function addPromptField(modalEl, options) {
    removePromptField(modalEl);
    var desc = modalEl.querySelector('.logout-modal-desc');
    var wrap = document.createElement('div');
    wrap.className = 'logout-modal-prompt-wrap';
    wrap.style.margin = '-12px 0 24px';
    wrap.innerHTML = [
      '<input type="text" class="logout-modal-prompt" autocomplete="off">',
    ].join('');
    var input = wrap.querySelector('input');
    input.value = options.defaultValue || '';
    input.placeholder = options.placeholder || '';
    input.style.width = '100%';
    input.style.height = '46px';
    input.style.border = '1px solid #d1d5db';
    input.style.borderRadius = '12px';
    input.style.padding = '0 14px';
    input.style.fontSize = '15px';
    input.style.color = '#111827';
    input.style.outline = 'none';
    input.addEventListener('focus', function () {
      input.style.borderColor = '#d4af37';
      input.style.boxShadow = '0 0 0 3px rgba(212,175,55,.16)';
    });
    input.addEventListener('blur', function () {
      input.style.borderColor = '#d1d5db';
      input.style.boxShadow = 'none';
    });
    desc.insertAdjacentElement('afterend', wrap);
    return input;
  }

  function showDialog(options) {
    return new Promise(function (resolve) {
      var modalEl = ensureDialogModal();
      if (!window.bootstrap || !window.bootstrap.Modal) {
        resolve(options.mode === 'prompt' ? null : false);
        return;
      }

      var titleEl = modalEl.querySelector('.logout-modal-title');
      var descEl = modalEl.querySelector('.logout-modal-desc');
      var iconEl = modalEl.querySelector('.logout-modal-icon');
      var actionsEl = modalEl.querySelector('.logout-modal-actions');
      var cancelBtn = replaceButton(modalEl.querySelector('.btn-cancel'));
      var confirmBtn = replaceButton(modalEl.querySelector('.btn-logout-confirm'));
      var inputEl = null;
      var settled = false;
      var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);

      titleEl.textContent = options.title || 'Thông báo';
      descEl.textContent = options.message || '';
      iconEl.textContent = options.iconText || '!';
      cancelBtn.textContent = options.cancelText || 'Hủy';
      confirmBtn.textContent = options.confirmText || 'OK';
      cancelBtn.style.display = options.showCancel === false ? 'none' : '';
      actionsEl.style.gap = options.showCancel === false ? '0' : '14px';

      if (options.mode === 'prompt') {
        inputEl = addPromptField(modalEl, options);
      } else {
        removePromptField(modalEl);
      }

      function done(value) {
        if (settled) return;
        settled = true;
        modal.hide();
        resolve(value);
      }

      cancelBtn.addEventListener('click', function () {
        done(options.mode === 'prompt' ? null : false);
      }, { once: true });

      confirmBtn.addEventListener('click', function () {
        if (options.mode === 'prompt') {
          done(inputEl ? inputEl.value : '');
        } else {
          done(true);
        }
      }, { once: true });

      modalEl.addEventListener('hidden.bs.modal', function () {
        if (!settled) {
          settled = true;
          resolve(options.mode === 'prompt' ? null : false);
        }
      }, { once: true });

      modal.show();
      if (inputEl) {
        setTimeout(function () { inputEl.focus(); }, 180);
      } else {
        setTimeout(function () { confirmBtn.focus(); }, 180);
      }
    });
  }

  window.showAlert = function showAlert(message, options) {
    options = options || {};
    return showDialog({
      mode: 'alert',
      title: options.title || 'Thông báo',
      message: message,
      confirmText: options.confirmText || 'OK',
      showCancel: false
    }).then(function () {});
  };

  window.showConfirm = function showConfirm(message, options) {
    options = options || {};
    return showDialog({
      mode: 'confirm',
      title: options.title || 'Xác nhận',
      message: message,
      confirmText: options.confirmText || 'Xác nhận',
      cancelText: options.cancelText || 'Hủy',
      showCancel: true
    });
  };

  window.showPrompt = function showPrompt(message, options) {
    options = options || {};
    return showDialog({
      mode: 'prompt',
      title: options.title || 'Nhập thông tin',
      message: message,
      confirmText: options.confirmText || 'Xác nhận',
      cancelText: options.cancelText || 'Hủy',
      defaultValue: options.defaultValue || '',
      placeholder: options.placeholder || '',
      showCancel: true
    });
  };
})();
