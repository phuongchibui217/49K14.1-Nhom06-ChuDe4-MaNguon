/**
 * FilterManager — Shared filter behavior cho toàn hệ thống Spa ANA
 *
 * Rule cốt lõi:
 *  - Nút hiện "Lọc"    khi form chưa apply HOẶC state hiện tại ≠ applied state
 *  - Nút hiện "Bỏ lọc" CHỈ khi state hiện tại = applied state (đã apply và chưa thay đổi)
 *  - Enter trong ô search = nhấn nút Lọc
 *  - Nhấn "Bỏ lọc" → reset tất cả fields → chạy applyFn → nút về "Lọc"
 *
 * Cách dùng (JS-driven pages — appointments, staff, customers):
 *
 *   const fm = new FilterManager({
 *     fields: ['searchInput', 'statusFilter', 'serviceFilter'],  // id của các field
 *     btnId:  'schedFilterBtn',
 *     onApply: () => refreshData(),
 *     onClear: () => { ... reset extra state ... },   // optional
 *   });
 *
 * Cách dùng (form-GET pages — services, complaints):
 *
 *   FilterManager.initFormPage({
 *     formId:  'searchFilterForm',
 *     btnId:   'filterBtn',
 *     fields:  ['searchInput', 'categoryFilter', 'statusFilter'],
 *   });
 *   // Nút sẽ tự detect applied state từ URL query string khi load trang
 *
 * @version 1.0.0
 */
class FilterManager {
  /**
   * @param {object} opts
   * @param {string[]}  opts.fields   - Mảng id của các filter field (input/select)
   * @param {string}    opts.btnId    - Id của nút Lọc/Bỏ lọc
   * @param {function}  opts.onApply  - Callback khi apply filter (bắt buộc)
   * @param {function}  [opts.onClear]- Callback bổ sung khi clear (optional)
   * @param {string}    [opts.searchId] - Id của ô search chính (để bind Enter key)
   */
  constructor({ fields = [], btnId, onApply, onClear, searchId } = {}) {
    this._fields   = fields;
    this._btn      = document.getElementById(btnId);
    this._onApply  = onApply;
    this._onClear  = onClear || null;
    this._searchId = searchId || fields[0] || null;

    // Snapshot state đã apply gần nhất (null = chưa apply lần nào)
    this._appliedState = null;

    if (!this._btn) return;
    this._init();
  }

  // ── Public API ──────────────────────────────────────────────

  /** Đọc state hiện tại của tất cả fields */
  getState() {
    const state = {};
    this._fields.forEach(id => {
      const el = document.getElementById(id);
      if (el) state[id] = el.value;
    });
    return state;
  }

  /** Kiểm tra state hiện tại có khác applied state không */
  isDirty() {
    if (this._appliedState === null) return this._hasAnyValue();
    const cur = this.getState();
    return JSON.stringify(cur) !== JSON.stringify(this._appliedState);
  }

  /** Kiểm tra có field nào có giá trị không */
  _hasAnyValue() {
    return this._fields.some(id => {
      const el = document.getElementById(id);
      return el && el.value.trim() !== '';
    });
  }

  /** Apply filter: snapshot state, gọi callback, cập nhật nút */
  apply() {
    this._appliedState = this.getState();
    if (this._onApply) this._onApply();
    this._syncBtn();
  }

  /** Clear filter: reset fields, xóa snapshot, gọi callback, cập nhật nút */
  clear() {
    this._fields.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      if (el.tagName === 'SELECT') el.value = el.options[0]?.value ?? '';
      else el.value = '';
    });
    this._appliedState = null;
    if (this._onClear) this._onClear();
    if (this._onApply) this._onApply();
    this._syncBtn();
  }

  /** Cập nhật text/style nút dựa trên state */
  _syncBtn() {
    if (!this._btn) return;
    const isApplied = this._appliedState !== null && !this.isDirty();
    // Xóa cả 2 class trạng thái rồi thêm lại đúng class
    this._btn.classList.remove('btn-secondary', 'btn-outline-secondary', 'btn-primary');
    if (isApplied) {
      this._btn.classList.add('btn-outline-secondary');
      this._btn.innerHTML = '<i class="fas fa-rotate-left me-1"></i>Bỏ lọc';
    } else {
      this._btn.classList.add('btn-secondary');
      this._btn.innerHTML = '<i class="fas fa-filter me-1"></i>Lọc';
    }
  }

  // ── Private ─────────────────────────────────────────────────

  _init() {
    // Click nút: toggle apply/clear
    this._btn.addEventListener('click', () => {
      const isApplied = this._appliedState !== null && !this.isDirty();
      if (isApplied) {
        this.clear();
      } else {
        this.apply();
      }
    });

    // Enter trong ô search chính → apply
    if (this._searchId) {
      const searchEl = document.getElementById(this._searchId);
      if (searchEl) {
        searchEl.addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); this.apply(); }
        });
      }
    }

    // Khi user thay đổi bất kỳ field nào → re-sync nút
    this._fields.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const evt = (el.tagName === 'SELECT') ? 'change' : 'input';
      el.addEventListener(evt, () => this._syncBtn());
    });

    // Sync lần đầu
    this._syncBtn();
  }

  // ── Static helper cho form-GET pages ────────────────────────

  /**
   * Khởi tạo filter cho trang dùng form GET (submit reload trang).
   * Tự detect applied state từ URL query string.
   *
   * @param {object} opts
   * @param {string}   opts.formId  - Id của form
   * @param {string}   opts.btnId   - Id của nút submit/clear
   * @param {string[]} opts.fields  - Id của các filter field
   * @param {string}   [opts.clearUrl] - URL để redirect khi clear (mặc định: location.pathname)
   */
  static initFormPage({ formId, btnId, fields = [], clearUrl } = {}) {
    const form = document.getElementById(formId);
    const btn  = document.getElementById(btnId);
    if (!form || !btn) return;

    const params    = new URLSearchParams(window.location.search);
    const isApplied = fields.some(id => {
      const el = document.getElementById(id);
      if (!el) return false;
      // Lấy tên param từ attribute name của element
      const paramName = el.getAttribute('name') || id;
      return params.has(paramName) && params.get(paramName).trim() !== '';
    });

    function syncBtn(applied) {
      btn.classList.remove('btn-secondary', 'btn-outline-secondary', 'btn-primary');
      if (applied) {
        btn.classList.add('btn-outline-secondary');
        btn.innerHTML = '<i class="fas fa-rotate-left me-1"></i>Bỏ lọc';
        btn.type = 'button';
      } else {
        btn.classList.add('btn-secondary');
        btn.innerHTML = '<i class="fas fa-filter me-1"></i>Lọc';
        btn.type = 'submit';
      }
    }

    // Trạng thái ban đầu dựa trên URL
    syncBtn(isApplied);
    let _applied = isApplied;

    // Khi user thay đổi field → nút về "Lọc" (dirty)
    fields.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const evt = (el.tagName === 'SELECT') ? 'change' : 'input';
      el.addEventListener(evt, () => {
        // Nếu đang ở trạng thái applied và user thay đổi → dirty → "Lọc"
        if (_applied) { syncBtn(false); _applied = false; }
      });
    });

    // Enter trong ô search → submit form
    fields.forEach(id => {
      const el = document.getElementById(id);
      if (!el || el.tagName === 'SELECT') return;
      el.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); form.submit(); }
      });
    });

    // Click nút
    btn.addEventListener('click', e => {
      if (_applied) {
        // Đang "Bỏ lọc" → clear
        e.preventDefault();
        window.location.href = clearUrl || window.location.pathname;
      } else {
        // Đang "Lọc" → submit form (btn.type = 'submit' nên form tự submit)
        // Không cần làm gì thêm
      }
    });
  }
}
