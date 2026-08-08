/* ============================================================
   Trợ lý Pháp chế Tín dụng — Đăng nhập / Đăng xuất
   Nạp TRƯỚC app.js. Ứng dụng chính chỉ được dựng sau khi có phiên hợp lệ.
   ============================================================ */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const state = {
    me: null,
    trangThai: null,      // kết quả /api/auth/status
    cheDo: "login",       // login | register
    dangGui: false,
    daDungApp: false,     // app.js đã chạy init() hay chưa
    khoiDongApp: null,
    hetPhien: false,
  };

  /* ---------------- Gọi API ---------------- */
  async function goi(duongDan, tuyChon = {}) {
    const res = await fetch(duongDan, {
      credentials: "same-origin",
      headers: tuyChon.body ? { "Content-Type": "application/json" } : undefined,
      ...tuyChon,
    });
    let dl = null;
    try { dl = await res.json(); } catch (e) { /* phản hồi rỗng */ }
    if (!res.ok) {
      const loi = new Error((dl && dl.detail) || res.statusText || "Lỗi máy chủ");
      loi.status = res.status;
      throw loi;
    }
    return dl;
  }

  const gui = (duongDan, than, phuongThuc = "POST") =>
    goi(duongDan, { method: phuongThuc, body: JSON.stringify(than) });

  /* ============================================================
     MÀN HÌNH ĐĂNG NHẬP
     ============================================================ */
  const TRUONG = {
    login: [
      { k: "username", l: "Tên đăng nhập", type: "text", ph: "vd: nguyenvana", auto: "username" },
      { k: "password", l: "Mật khẩu", type: "password", ph: "••••••••", auto: "current-password" },
    ],
    register: [
      { k: "username", l: "Tên đăng nhập", type: "text", ph: "chữ thường, số, dấu . _ -", auto: "username",
        hint: "Từ 3 đến 32 ký tự, không dấu và không khoảng trắng." },
      { k: "ho_ten", l: "Họ và tên", type: "text", ph: "vd: Nguyễn Văn A", auto: "name", tuyChon: true },
      { k: "email", l: "Email", type: "email", ph: "vd: an@congty.vn", auto: "email", tuyChon: true },
      { k: "password", l: "Mật khẩu", type: "password", ph: "ít nhất 8 ký tự", auto: "new-password" },
      { k: "password2", l: "Nhập lại mật khẩu", type: "password", ph: "gõ lại mật khẩu", auto: "new-password" },
    ],
  };

  function veForm() {
    const cheDo = state.cheDo;
    const dauTien = state.trangThai && !state.trangThai.da_co_tai_khoan;
    const choPhepDangKy = !state.trangThai || state.trangThai.cho_phep_dang_ky;

    $("authTabs").hidden = dauTien || !choPhepDangKy;
    document.querySelectorAll(".auth-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === cheDo);
    });

    const tieuDe = dauTien
      ? { h: "Thiết lập quản trị viên", p: "Chưa có tài khoản nào trong hệ thống. Tài khoản bạn tạo đầu tiên sẽ là quản trị viên, có quyền nạp văn bản pháp luật và quản lý người dùng." }
      : cheDo === "login"
        ? { h: "Đăng nhập", p: "Nhập tài khoản để vào khu vực tra cứu và lập hồ sơ." }
        : { h: "Tạo tài khoản", p: "Hồ sơ và dữ liệu bạn nhập sẽ được lưu riêng theo tài khoản này." };

    const truong = TRUONG[cheDo].map((f) => `
      <div class="f">
        <label for="au-${f.k}">${esc(f.l)}${f.tuyChon ? '<span class="opt">không bắt buộc</span>' : '<span class="req">*</span>'}</label>
        <input class="ctrl" id="au-${f.k}" name="${f.k}" type="${f.type}"
               placeholder="${esc(f.ph)}" autocomplete="${f.auto}"
               ${f.tuyChon ? "" : "required"} />
        ${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ""}
      </div>`).join("");

    $("authForm").innerHTML = `
      <div class="auth-head">
        <h2>${esc(tieuDe.h)}</h2>
        <p>${esc(tieuDe.p)}</p>
      </div>
      ${state.hetPhien ? '<div class="auth-msg warn">Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.</div>' : ""}
      <div class="auth-msg err" id="authErr" hidden></div>
      ${truong}
      ${cheDo === "login" ? `
        <label class="switch auth-remember">
          <input type="checkbox" id="au-ghinho" checked />
          <span>Ghi nhớ đăng nhập trên máy này</span>
        </label>` : ""}
      <button class="btn primary lg block" id="authSubmit" type="submit">
        ${dauTien ? "Tạo quản trị viên" : cheDo === "login" ? "Đăng nhập" : "Tạo tài khoản"}
      </button>
      ${choPhepDangKy && !dauTien ? `
        <div class="auth-alt">
          ${cheDo === "login"
            ? 'Chưa có tài khoản? <button type="button" data-mode="register">Đăng ký ngay</button>'
            : 'Đã có tài khoản? <button type="button" data-mode="login">Đăng nhập</button>'}
        </div>` : ""}`;

    $("authForm").querySelectorAll("[data-mode]").forEach((b) => {
      b.onclick = () => { state.cheDo = b.dataset.mode; veForm(); };
    });
    const dau = $("authForm").querySelector("input");
    if (dau) setTimeout(() => dau.focus(), 60);
  }

  function baoLoi(text) {
    const box = $("authErr");
    if (!box) return;
    box.hidden = !text;
    box.textContent = text || "";
    if (text) box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function dangGui(on) {
    state.dangGui = on;
    const nut = $("authSubmit");
    if (nut) {
      nut.disabled = on;
      nut.textContent = on ? "Đang xử lý…" : nut.dataset.nhan || nut.textContent;
    }
  }

  async function nopForm(e) {
    e.preventDefault();
    if (state.dangGui) return;

    const lay = (k) => ($("au-" + k) ? $("au-" + k).value : "");
    const cheDo = state.cheDo;
    baoLoi("");

    if (cheDo === "register" && lay("password") !== lay("password2")) {
      baoLoi("Hai lần nhập mật khẩu không giống nhau.");
      return;
    }

    const nut = $("authSubmit");
    if (nut) nut.dataset.nhan = nut.textContent;
    dangGui(true);

    try {
      const than = cheDo === "login"
        ? { username: lay("username"), password: lay("password"), ghi_nho: $("au-ghinho") ? $("au-ghinho").checked : true }
        : { username: lay("username"), password: lay("password"), ho_ten: lay("ho_ten"), email: lay("email") };

      const kq = await gui("/api/auth/" + (cheDo === "login" ? "login" : "register"), than);
      await vaoUngDung(kq.nguoi_dung);
    } catch (err) {
      baoLoi(err.message || "Không đăng nhập được.");
      dangGui(false);
    }
  }

  /* ============================================================
     CHUYỂN GIỮA MÀN HÌNH ĐĂNG NHẬP VÀ ỨNG DỤNG
     ============================================================ */
  function moKhoa() {
    $("authShell").hidden = true;
    document.body.classList.remove("locked");
  }

  function khoa() {
    $("authShell").hidden = false;
    document.body.classList.add("locked");
    veForm();
  }

  async function vaoUngDung(nguoiDung) {
    state.me = nguoiDung;
    // Đăng nhập lại sau khi ứng dụng đã dựng: tải lại trang cho sạch trạng thái cũ.
    if (state.daDungApp) { location.reload(); return; }
    moKhoa();
    veChipNguoiDung();
    state.daDungApp = true;
    if (typeof state.khoiDongApp === "function") await state.khoiDongApp();
  }

  function veChipNguoiDung() {
    const u = state.me;
    if (!u) return;
    const chip = $("userChip");
    if (!chip) return;
    chip.hidden = false;
    const ten = (u.ho_ten || u.username || "?").trim();
    $("userAvatar").textContent = ten.charAt(0).toUpperCase();
    $("userName").textContent = ten;
    $("userRole").textContent = u.vai_tro === "admin" ? "Quản trị viên" : "Người dùng";
    chip.classList.toggle("admin", u.vai_tro === "admin");
  }

  /* ---------------- Menu tài khoản ---------------- */
  function dongMenu() {
    const m = $("userMenu");
    if (m) m.hidden = true;
  }

  function ganMenu() {
    const nut = $("btnUser"), menu = $("userMenu");
    if (!nut || !menu) return;

    nut.onclick = (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; };
    document.addEventListener("click", dongMenu);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") dongMenu(); });
    menu.onclick = (e) => e.stopPropagation();

    menu.querySelectorAll("[data-act]").forEach((b) => {
      b.onclick = async () => {
        dongMenu();
        const act = b.dataset.act;
        if (act === "logout") return API_CONG_KHAI.dangXuat();
        if (act === "logout-all") return dangXuatMoiNoi();
        if (act === "password") return moDoiMatKhau();
        if (act === "data" && window.switchView) window.switchView("data");
      };
    });
  }

  async function dangXuatMoiNoi() {
    if (!confirm("Đăng xuất khỏi tất cả thiết bị khác? Phiên trên máy này vẫn giữ nguyên.")) return;
    try {
      const kq = await gui("/api/auth/logout-all", {});
      window.toast?.(`Đã đóng ${kq.da_dong_phien} phiên trên thiết bị khác`, "ok");
    } catch (err) {
      window.toast?.("Lỗi: " + err.message, "err");
    }
  }

  /* ---------------- Hộp thoại nhỏ dùng chung ---------------- */
  function moHopThoai({ tieuDe, mo_ta, truong, nhanNut, xuLy }) {
    const cu = $("authDialog");
    if (cu) cu.remove();

    const el = document.createElement("div");
    el.className = "dlg-back";
    el.id = "authDialog";
    el.innerHTML = `
      <form class="dlg">
        <h3>${esc(tieuDe)}</h3>
        ${mo_ta ? `<p class="dlg-sub">${esc(mo_ta)}</p>` : ""}
        <div class="auth-msg err" id="dlgErr" hidden></div>
        ${truong.map((f) => `
          <div class="f">
            <label for="dlg-${f.k}">${esc(f.l)}</label>
            <input class="ctrl" id="dlg-${f.k}" type="${f.type || "text"}"
                   placeholder="${esc(f.ph || "")}" autocomplete="${f.auto || "off"}"
                   value="${esc(f.gia_tri || "")}" ${f.tuyChon ? "" : "required"} />
          </div>`).join("")}
        <div class="dlg-actions">
          <button type="button" class="btn" id="dlgCancel">Huỷ</button>
          <button type="submit" class="btn primary" id="dlgOk">${esc(nhanNut || "Xác nhận")}</button>
        </div>
      </form>`;
    document.body.appendChild(el);

    const dong = () => el.remove();
    $("dlgCancel").onclick = dong;
    el.onclick = (e) => { if (e.target === el) dong(); };

    el.querySelector("form").onsubmit = async (e) => {
      e.preventDefault();
      const gt = {};
      truong.forEach((f) => { gt[f.k] = $("dlg-" + f.k).value; });
      const ok = $("dlgOk");
      ok.disabled = true;
      const nhanCu = ok.textContent;
      ok.textContent = "Đang xử lý…";
      try {
        await xuLy(gt);
        dong();
      } catch (err) {
        const box = $("dlgErr");
        box.hidden = false;
        box.textContent = err.message || "Có lỗi xảy ra.";
        ok.disabled = false;
        ok.textContent = nhanCu;
      }
    };
    setTimeout(() => el.querySelector("input")?.focus(), 60);
  }

  function moDoiMatKhau() {
    moHopThoai({
      tieuDe: "Đổi mật khẩu",
      mo_ta: "Sau khi đổi, mọi thiết bị khác đang đăng nhập sẽ bị đăng xuất.",
      nhanNut: "Đổi mật khẩu",
      truong: [
        { k: "cu", l: "Mật khẩu hiện tại", type: "password", auto: "current-password" },
        { k: "moi", l: "Mật khẩu mới", type: "password", auto: "new-password", ph: "ít nhất 8 ký tự" },
        { k: "moi2", l: "Nhập lại mật khẩu mới", type: "password", auto: "new-password" },
      ],
      xuLy: async (gt) => {
        if (gt.moi !== gt.moi2) throw new Error("Hai lần nhập mật khẩu mới không giống nhau.");
        await gui("/api/auth/change-password", {
          mat_khau_cu: gt.cu, mat_khau_moi: gt.moi, dang_xuat_thiet_bi_khac: true,
        });
        window.toast?.("Đã đổi mật khẩu", "ok");
      },
    });
  }

  /* ============================================================
     GIAO DIỆN CÔNG KHAI CHO app.js
     ============================================================ */
  const API_CONG_KHAI = {
    get me() { return state.me; },
    get id() { return state.me ? state.me.id : "guest"; },
    laQuanTri() { return !!state.me && state.me.vai_tro === "admin"; },

    goi,
    gui,
    moHopThoai,
    moDoiMatKhau,

    /** app.js gọi ở cuối file: kiểm tra phiên rồi mới dựng ứng dụng. */
    async boot(khoiDongApp) {
      state.khoiDongApp = khoiDongApp;
      $("authForm").addEventListener("submit", nopForm);
      document.querySelectorAll(".auth-tab").forEach((b) => {
        b.onclick = () => { state.cheDo = b.dataset.mode; veForm(); };
      });
      ganMenu();

      try {
        state.trangThai = await goi("/api/auth/status");
      } catch (err) {
        state.trangThai = { dang_nhap: false, cho_phep_dang_ky: true, da_co_tai_khoan: true };
      }

      if (state.trangThai.dang_nhap && state.trangThai.nguoi_dung) {
        await vaoUngDung(state.trangThai.nguoi_dung);
      } else {
        state.cheDo = state.trangThai.da_co_tai_khoan ? "login" : "register";
        khoa();
      }
    },

    async dangXuat() {
      if (!confirm("Đăng xuất khỏi tài khoản?")) return;
      try { await gui("/api/auth/logout", {}); } catch (e) { /* vẫn cho thoát */ }
      location.reload();
    },

    /** Phiên hết hạn giữa chừng — khoá màn hình lại thay vì để lỗi 401 lan khắp nơi. */
    phienHetHan() {
      if (state.hetPhien) return;
      state.hetPhien = true;
      state.me = null;
      state.cheDo = "login";
      khoa();
    },

    /** Trả về true nếu phản hồi là 401 và đã xử lý xong. */
    la401(res) {
      if (res && res.status === 401) { API_CONG_KHAI.phienHetHan(); return true; }
      return false;
    },

    async lamMoi() {
      state.me = await goi("/api/auth/me");
      veChipNguoiDung();
      return state.me;
    },
  };

  window.Auth = API_CONG_KHAI;
})();
