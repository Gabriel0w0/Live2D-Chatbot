// =================== 全域變數/工具 ===================
let lastAudioUrl = null;
let currentAudio = null;
let userHasInteracted = false;
let intimacyLevel = Number(localStorage.getItem("intimacyLevel")) || 50;

// =================== 全域狀態管理 ===================
const AppState = {
  isResearching: false,
  isChatting: false,

  isBusy() {
    return this.isResearching || this.isChatting;
  },

  getBusyReason() {
    if (this.isResearching) return '研究進行中';
    if (this.isChatting) return '等待回覆中';
    return null;
  }
};
window.AppState = AppState;

// =================== Toast 通知系統 ===================
function showToast(message, type = 'info', duration = 3000) {
  const oldToast = document.querySelector('.toast-notification');
  if (oldToast) oldToast.remove();

  const toast = document.createElement('div');
  toast.className = `toast-notification toast-${type}`;

  const icons = {
    'success': 'fa-check-circle',
    'warning': 'fa-exclamation-circle',
    'error': 'fa-times-circle',
    'info': 'fa-info-circle'
  };

  toast.innerHTML = `
    <i class="fas ${icons[type] || icons.info}"></i>
    <span>${message}</span>
  `;

  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
window.showToast = showToast;

// 音訊許可（點擊/按鍵）
document.addEventListener("click", () => userHasInteracted = true, { once: true });
document.addEventListener("keydown", () => userHasInteracted = true, { once: true });

// TTS 播放與重播
function safePlayAudio(url) {
  if (!userHasInteracted) {
    console.warn("尚未有使用者互動，音訊播放被跳過");
    return;
  }
  currentAudio = new Audio(url);
  currentAudio.addEventListener("canplaythrough", () => {
    currentAudio.play().catch(err => console.warn("播放語音失敗：", err));
  });
}

function replayLastAudio() {
  if (!lastAudioUrl) {
    showToast('還沒有語音可以重播喔 (´;ω;`)', 'warning');
    return;
  }
  if (!userHasInteracted) {
    showToast('請先互動後才能播放語音 (´;ω;`)', 'warning');
    return;
  }
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
  }
  safePlayAudio(lastAudioUrl);
}
document.getElementById('replayAudio')?.addEventListener('click', replayLastAudio);

// 親密度顯示
function updateIntimacyDisplay() {
  let levelName = "冷淡";
  if (intimacyLevel >= 90) levelName = "羈絆";
  else if (intimacyLevel >= 60) levelName = "親密";
  else if (intimacyLevel >= 30) levelName = "普通";
  const textElem = document.getElementById("intimacy-text");
  const barElem = document.getElementById("intimacy-bar-fill");
  if (textElem) textElem.textContent = `親密度：${intimacyLevel} (${levelName})`;
  if (barElem) barElem.style.width = Math.min(100, Math.max(0, intimacyLevel)) + "%";
}

// 防XSS
function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return text.replace(/[&<>"']/g, m => map[m]);
}

// =================== 主應用 IIFE ===================
(function () {
  'use strict';

  // ========== 1. 權限/條款 Modal ==========
  function initAudioPermission() {
    const overlay = document.getElementById("audio-permission-overlay");
    overlay.style.transition = "opacity 0.6s ease";
    overlay.style.opacity = "0";
    setTimeout(() => overlay.style.display = "none", 600);
    localStorage.setItem("hasVisited", "true");
  }
  function showTerms() { document.getElementById("termsModal").style.display = "block"; }
  function closeTerms() { document.getElementById("termsModal").style.display = "none"; }
  window.initAudioPermission = initAudioPermission;
  window.showTerms = showTerms;
  window.closeTerms = closeTerms;

  document.addEventListener("DOMContentLoaded", function () {
    const overlay = document.getElementById("audio-permission-overlay");
    overlay.style.display = localStorage.getItem("hasVisited") ? "none" : "flex";
    document.getElementById("startChatBtn").onclick = initAudioPermission;
    document.getElementById("showTermsBtn").onclick = showTerms;
    document.getElementById("closeTermsBtn").onclick = closeTerms;
    document.getElementById("termsModal").onclick = function (e) {
      if (e.target === this) closeTerms();
    };
    updateIntimacyDisplay();
  });

  // ========== 2. 背景粒子 ==========
  tsParticles.load("particles-js", {
    fpsLimit: 60,
    background: { color: "#111" },
    particles: {
      number: { value: 40, density: { enable: true, area: 800 } },
      color: { value: ["#a58aff", "#ff92c8", "#8844cc"] },
      shape: { type: "circle" },
      opacity: {
        value: 0.5,
        random: true,
        anim: { enable: true, speed: 0.5, opacity_min: 0.1, sync: false }
      },
      size: {
        value: 3,
        random: true,
        anim: { enable: true, speed: 3, size_min: 1, sync: false }
      },
      move: {
        enable: true,
        speed: 1,
        direction: "none",
        random: true,
        straight: false,
        outModes: "out"
      }
    },
    interactivity: {
      events: {
        onHover: { enable: true, mode: "grab" },
        onClick: { enable: true, mode: "push" }
      },
      modes: {
        grab: { distance: 140, links: { opacity: 0.5 } },
        push: { quantity: 3 }
      }
    },
    detectRetina: true
  });

  // ========== 3. Live2D 控制器 ==========
  class Live2DController {
    constructor() {
      this.model = null;
      this.app = null;
      this.lastAudio = null;
    }

    async init() {
      const live2dPanel = document.querySelector('.live2d-panel');
      if (!live2dPanel) return;
      this.app = new PIXI.Application({
        width: 400,
        height: live2dPanel.clientHeight,
        backgroundAlpha: 0,
        resizeTo: live2dPanel
      });
      document.getElementById('live2d-area').appendChild(this.app.view);

      try {
        this.model = await PIXI.live2d.Live2DModel.from(
          "/static/model/hiyori/runtime/hiyori_pro_t11.model3.json"
        );
        window.live2dModel = this.model;
        this.model.scale.set(0.17);
        this.model.anchor.set(0.5, 0.5);
        this.model.x = this.app.renderer.width / 2;
        this.model.y = this.app.renderer.height / 2;
        this.app.stage.addChild(this.model);
        this.app.renderer.render(this.app.stage);
        window.addEventListener("resize", () => this.handleResize());
      } catch (err) {
        console.error("載入Live2D模型失敗:", err);
      }
    }

    handleResize() {
      if (!this.model || !this.app) return;
      const live2dPanel = document.querySelector('.live2d-panel');
      this.app.renderer.resize(400, live2dPanel.clientHeight);
      this.model.x = this.app.renderer.width / 2;
      this.model.y = this.app.renderer.height / 2;
      this.app.renderer.render(this.app.stage);
    }

    playMotion(motionName) {
      if (!this.model) {
        console.warn("Live2D模型尚未載入");
        return;
      }
      try {
        this.model.motion(motionName);
      } catch (err) {
        console.error("播放動作失敗:", err);
      }
    }

    replayAudio() {
      if (this.lastAudio) {
        this.lastAudio.currentTime = 0;
        this.lastAudio.play();
      }
    }
  }

  // ========== 4. 聊天管理器 ==========
  function removeEmotionTag(text) {
    return text.replace(/\[emotion:\w+\]/gi, "").trim();
  }

  class ChatManager {
    constructor() {
      this.storageKey = 'tsukuyomi_chat_data';
      this.data = this.loadData();
      this.currentRoom = null;
      this.chatHistory = document.querySelector('.chat-history');
      this.chatMessages = document.getElementById('chat-messages');
      this.chatInput = document.getElementById('chatInput');
      this.sendBtn = document.getElementById('sendBtn');
      this.voiceInputBtn = document.getElementById('voiceInputBtn');
      this.recognition = null;
      this.voiceInputBaseValue = '';
      this.newChatBtn = document.querySelector('.new-chat-btn');
      this.typingIndicator = document.getElementById('typing-indicator');
      this.initEventListeners();
      this.renderSidebar();
      this.selectFirstRoom();
    }

    loadData() {
      try {
        const data = localStorage.getItem(this.storageKey);
        return data ? JSON.parse(data) : {};
      } catch (e) {
        console.error("載入聊天數據失敗:", e);
        return {};
      }
    }

    saveData() {
      try {
        localStorage.setItem(this.storageKey, JSON.stringify(this.data));
      } catch (e) {
        console.error("保存聊天數據失敗:", e);
      }
    }

    initEventListeners() {
      this.sendBtn.addEventListener('click', () => this.sendMessage());
      this.voiceInputBtn?.addEventListener('click', () => this.toggleVoiceInput());
      this.newChatBtn.addEventListener('click', () => this.createNewRoom());
      this.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.sendMessage();
        }
      });
      this.chatInput.addEventListener('input', (e) => {
        e.target.style.height = 'auto';
        e.target.style.height = (e.target.scrollHeight) + 'px';
      });
    }

    toggleVoiceInput() {
      if (this.recognition) {
        this.stopVoiceInput();
        return;
      }

      if (!window.isSecureContext) {
        showToast('語音輸入需要在 HTTPS 或 localhost 環境中使用。', 'warning');
        return;
      }

      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        showToast('目前的瀏覽器不支援語音辨識，請改用支援此功能的瀏覽器。', 'warning');
        return;
      }

      let recognition;
      try {
        recognition = new SpeechRecognition();
      } catch (error) {
        console.error('建立語音辨識失敗：', error);
        showToast('無法啟動語音輸入，請稍後再試。', 'error');
        return;
      }

      this.recognition = recognition;
      this.voiceInputBaseValue = this.chatInput.value;
      recognition.lang = 'zh-TW';
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onstart = () => {
        this.voiceInputBtn?.classList.add('is-recording');
        this.voiceInputBtn?.setAttribute('aria-pressed', 'true');
        this.voiceInputBtn?.setAttribute('aria-label', '停止語音輸入');
        this.voiceInputBtn?.setAttribute('title', '停止語音輸入');
      };

      recognition.onresult = (event) => {
        let transcript = '';
        for (let index = 0; index < event.results.length; index += 1) {
          transcript += event.results[index][0].transcript;
        }

        const separator = this.voiceInputBaseValue && !/\s$/.test(this.voiceInputBaseValue) ? ' ' : '';
        this.chatInput.value = `${this.voiceInputBaseValue}${separator}${transcript}`;
        this.chatInput.dispatchEvent(new Event('input', { bubbles: true }));
      };

      recognition.onerror = (event) => {
        const messages = {
          'not-allowed': '麥克風權限遭拒，請在瀏覽器設定中允許使用麥克風。',
          'service-not-allowed': '瀏覽器不允許使用語音辨識服務。',
          'audio-capture': '找不到可用的麥克風，請確認裝置已連接。',
          'no-speech': '沒有偵測到語音，請再試一次。',
          'network': '語音辨識服務連線失敗，請檢查網路後重試。'
        };

        if (event.error !== 'aborted') {
          showToast(messages[event.error] || '語音辨識發生錯誤，請稍後再試。', 'error');
        }
      };

      recognition.onend = () => {
        if (this.recognition !== recognition) return;
        this.recognition = null;
        this.voiceInputBtn?.classList.remove('is-recording');
        this.voiceInputBtn?.setAttribute('aria-pressed', 'false');
        this.voiceInputBtn?.setAttribute('aria-label', '語音輸入');
        this.voiceInputBtn?.setAttribute('title', '語音輸入');
      };

      try {
        recognition.start();
      } catch (error) {
        this.recognition = null;
        console.error('啟動語音辨識失敗：', error);
        showToast('無法啟動語音輸入，請稍後再試。', 'error');
      }
    }

    stopVoiceInput() {
      if (!this.recognition) return;

      try {
        this.recognition.stop();
      } catch (error) {
        console.error('停止語音辨識失敗：', error);
        showToast('無法停止語音輸入，請重新整理頁面後再試。', 'error');
      }
    }

    renderSidebar() {
      this.chatHistory.innerHTML = '';
      const items = Object.keys(this.data).map(title => ({
        title,
        pinned: this.data[title].pinned || false
      }));
      const pinned = items.filter(i => i.pinned);
      const unpinned = items.filter(i => !i.pinned);
      [...pinned, ...unpinned].forEach(item => {
        const li = document.createElement('li');
        li.className = 'chat-item' + (item.pinned ? ' pinned' : '');
        const icon = document.createElement('i');
        icon.className = 'fa fa-message';
        const title = document.createElement('span');
        title.className = 'chat-title';
        title.textContent = item.title;
        const pinBtn = document.createElement('button');
        pinBtn.type = 'button';
        pinBtn.className = 'pin-btn';
        pinBtn.title = '釘選/取消';
        pinBtn.innerHTML = '<i class="fa fa-thumbtack"></i>';
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'delete-btn';
        deleteBtn.title = '刪除';
        deleteBtn.innerHTML = '<i class="fa fa-trash"></i>';
        li.appendChild(icon);
        li.appendChild(title);
        li.appendChild(pinBtn);
        li.appendChild(deleteBtn);
        li.addEventListener('click', (e) => {
          if (e.target.closest('.pin-btn, .delete-btn')) return;
          this.selectRoom(item.title);
        });
        pinBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.togglePin(item.title);
        });
        deleteBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.deleteRoom(item.title);
        });
        let longPressTimer;
        title.addEventListener('mousedown', () => {
          longPressTimer = setTimeout(() => {
            this.renameRoom(item.title);
          }, 600);
        });
        title.addEventListener('mouseup', () => clearTimeout(longPressTimer));
        title.addEventListener('mouseleave', () => clearTimeout(longPressTimer));
        this.chatHistory.appendChild(li);
      });
    }

    selectRoom(roomTitle) {
      this.currentRoom = roomTitle;
      document.querySelectorAll('.chat-item').forEach(el =>
        el.classList.remove('active')
      );
      const activeItem = Array.from(document.querySelectorAll('.chat-item'))
        .find(el => el.querySelector('.chat-title').textContent === roomTitle);
      if (activeItem) activeItem.classList.add('active');
      this.renderMessages();
    }

    renderMessages() {
      if (!this.currentRoom) return;

      const typingIndicator = document.getElementById('typing-indicator');
      const isTyping = typingIndicator && !typingIndicator.classList.contains('hidden');

      const allChildren = Array.from(this.chatMessages.children);
      allChildren.forEach(child => {
        if (child.id !== 'typing-indicator') {
          child.remove();
        }
      });

      const messages = this.data[this.currentRoom]?.messages || [];
      messages.forEach(msg => {
        const div = document.createElement('div');
        div.className = `chat-message ${msg.role}`;
        div.textContent = msg.text;
        this.chatMessages.appendChild(div);
      });

      if (!document.getElementById('typing-indicator')) {
        const indicator = document.createElement('div');
        indicator.id = 'typing-indicator';
        indicator.className = 'chat-message bot typing-indicator hidden';
        indicator.innerHTML = '<div class="wave-dots"><span></span><span></span><span></span></div>';
        this.chatMessages.appendChild(indicator);
        this.typingIndicator = indicator;
      } else {
        this.chatMessages.appendChild(typingIndicator);
      }

      if (isTyping) {
        this.showTyping();
      }

      this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    sendMessage() {
      // ✅ 檢查是否忙碌
      if (AppState.isBusy()) {
        showToast(`${AppState.getBusyReason()}，請稍候喔～ `, 'warning');
        return;
      }

      if (!this.currentRoom || !this.chatInput.value.trim()) return;

      const userMessage = this.chatInput.value.trim();
      if (this.recognition) {
        this.recognition.onresult = null;
        this.stopVoiceInput();
      }

      if (!this.data[this.currentRoom]) {
        this.data[this.currentRoom] = { messages: [], pinned: false };
      }
      this.data[this.currentRoom].messages.push({
        role: 'user',
        text: userMessage
      });
      this.saveData();
      this.renderMessages();
      this.chatInput.value = '';
      this.chatInput.style.height = 'auto';

      // ✅ 設定忙碌狀態
      AppState.isChatting = true;
      this.disableInput();

      this.fetchBotResponse(userMessage);
    }

    showTyping() {
      if (!this.typingIndicator) {
        this.createTypingIndicator();
      }
      if (this.typingIndicator) {
        this.typingIndicator.classList.remove('hidden');
        this.chatMessages.appendChild(this.typingIndicator);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        const dots = this.typingIndicator.querySelectorAll('.wave-dots span');
        dots.forEach(dot => {
          dot.style.animation = 'none';
          dot.offsetHeight;
          dot.style.animation = null;
        });
      }
    }

    hideTyping() {
      if (this.typingIndicator) {
        this.typingIndicator.classList.add('hidden');
      }
    }

    // 禁用輸入
    disableInput() {
      if (this.chatInput) {
        this.chatInput.disabled = true;
        this.chatInput.placeholder = '月讀醬正在思考中...';
      }
      if (this.sendBtn) {
        this.sendBtn.disabled = true;
        this.sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
      }
      if (this.voiceInputBtn) this.voiceInputBtn.disabled = true;
      document.querySelectorAll('.nav-center a').forEach(link => {
        link.classList.add('nav-busy');
      });
    }

    // 啟用輸入
    enableInput() {
      if (this.chatInput) {
        this.chatInput.disabled = false;
        this.chatInput.placeholder = '詢問初音未來及V家的問題或單純的聊聊天吧(•ω•)/';
      }
      if (this.sendBtn) {
        this.sendBtn.disabled = false;
        this.sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
      }
      if (this.voiceInputBtn) this.voiceInputBtn.disabled = false;
      document.querySelectorAll('.nav-center a').forEach(link => {
        link.classList.remove('nav-busy');
      });
    }

    async fetchBotResponse(message) {
      this.showTyping();
      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message })
        });
        const data = await res.json();
        if (data.reply) {
          const cleanReply = removeEmotionTag(data.reply);
          this.data[this.currentRoom].messages.push({
            role: 'bot',
            text: cleanReply
          });
          this.saveData();
          this.renderMessages();
        }
        if (data.audio_url) {
          lastAudioUrl = data.audio_url;
          safePlayAudio(lastAudioUrl);
        }
        if (typeof data.intimacy === "number") {
          intimacyLevel = data.intimacy;
          updateIntimacyDisplay();
          localStorage.setItem("intimacyLevel", intimacyLevel);
        }
      } catch (err) {
        console.error("API 發生錯誤：", err);
        this.data[this.currentRoom].messages.push({
          role: 'bot',
          text: '出錯了喔！'
        });
        this.saveData();
        this.renderMessages();
      } finally {
        AppState.isChatting = false;
        this.enableInput();
        this.hideTyping();
      }
    }

    createNewRoom() {
      const title = prompt('請幫聊天室取個名字', '新聊天室');
      if (!title || !title.trim()) return;
      if (this.data[title.trim()]) {
        alert('聊天室名稱已存在！');
        return;
      }
      this.data[title.trim()] = { messages: [], pinned: false };
      this.saveData();
      this.renderSidebar();
      this.selectRoom(title.trim());
    }

    renameRoom(oldTitle) {
      const newTitle = prompt('請輸入新的聊天室名稱', oldTitle);
      if (!newTitle || !newTitle.trim() || newTitle === oldTitle) return;
      if (this.data[newTitle.trim()]) {
        alert('聊天室名稱已存在！');
        return;
      }
      this.data[newTitle.trim()] = this.data[oldTitle];
      delete this.data[oldTitle];
      if (this.currentRoom === oldTitle) {
        this.currentRoom = newTitle.trim();
      }
      this.saveData();
      this.renderSidebar();
      this.selectRoom(newTitle.trim());
    }

    deleteRoom(title) {
      if (!confirm('確定要刪除此聊天室？')) return;
      delete this.data[title];
      this.saveData();
      this.renderSidebar();
      if (this.currentRoom === title) {
        this.selectFirstRoom();
      }
    }

    togglePin(title) {
      this.data[title].pinned = !this.data[title].pinned;
      this.saveData();
      this.renderSidebar();
      this.selectRoom(title);
    }

    selectFirstRoom() {
      const firstRoom = Object.keys(this.data)[0];
      if (firstRoom) {
        this.selectRoom(firstRoom);
      } else {
        this.currentRoom = null;
        this.chatMessages.innerHTML = '';
      }
    }

    clearSession() {
      if (!this.currentRoom) return;
      if (!confirm('確定要清除短期記憶嗎？這會讓她忘記剛剛聊的內容喔！')) return;
      this.data[this.currentRoom].messages = [];
      this.saveData();
      this.renderMessages();
    }

    clearAllMemory() {
      if (!confirm('確定要清除所有記憶嗎？她會忘記所有過去的事情喔！')) return;
      this.data = {};
      this.currentRoom = null;
      this.saveData();
      this.renderSidebar();
      this.chatMessages.innerHTML = '';
    }
  }

  // =================== Researcher 介面 ===================

  // ========== 1. 搜索建議與自動完成 ==========
  class SearchSuggestionManager {
    constructor() {
      this.input = document.getElementById('researchInput');
      this.suggestionsContainer = document.getElementById('searchSuggestions');
      this.suggestionHistory = this.loadHistory();
      this.popularTopics = [
        { text: '大型語言模型最新發展', icon: 'fa-brain' },
        { text: '台灣半導體產業趨勢', icon: 'fa-microchip' },
        { text: '永續能源技術創新', icon: 'fa-leaf' },
      ];
      this.init();
    }

    init() {
      if (!this.input || !this.suggestionsContainer) return;

      this.input.addEventListener('input', (e) => this.handleInput(e));

      // ✅ 修復：focus 時顯示預設建議
      this.input.addEventListener('focus', () => {
        const currentValue = this.input.value.trim();
        if (currentValue.length === 0) {
          // 輸入框為空時，顯示預設建議
          this.showDefaultSuggestions();
        } else {
          // 輸入框有內容時，顯示過濾後的建議
          this.updateSuggestions(currentValue);
        }
      });

      document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box-wrapper')) {
          this.hideSuggestions();
        }
      });
    }

    handleInput(e) {
      const query = e.target.value.trim();
      if (query.length > 0) {
        this.updateSuggestions(query);
      } else {
        this.showDefaultSuggestions();
      }
    }

    updateSuggestions(query) {
      const filtered = this.popularTopics.filter(topic =>
        topic.text.toLowerCase().includes(query.toLowerCase())
      );

      const historyMatches = this.suggestionHistory.filter(item =>
        item.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 3);

      this.renderSuggestions([...historyMatches, ...filtered]);
    }

    showDefaultSuggestions() {
      this.renderSuggestions(this.popularTopics);
    }

    renderSuggestions(items) {
      if (!this.suggestionsContainer) return;

      this.suggestionsContainer.innerHTML = '';

      items.forEach(item => {
        const li = document.createElement('li');
        li.className = 'search-suggestion-item';

        const text = typeof item === 'string' ? item : item.text;
        const icon = typeof item === 'string' ? 'fa-history' : item.icon;

        li.innerHTML = `
          <i class="fas ${icon}"></i>
          <span class="suggestion-text">${escapeHtml(text)}</span>
        `;

        li.addEventListener('click', () => {
          this.input.value = text;
          this.hideSuggestions();
          this.saveToHistory(text);
          const startBtn = document.getElementById('startResearchBtn');
          if (startBtn) startBtn.click();
        });

        this.suggestionsContainer.appendChild(li);
      });

      this.showSuggestions();
    }

    showSuggestions() {
      if (this.suggestionsContainer) {
        this.suggestionsContainer.classList.remove('hidden');
      }
    }

    hideSuggestions() {
      if (this.suggestionsContainer) {
        this.suggestionsContainer.classList.add('hidden');
      }
    }

    saveToHistory(query) {
      if (!this.suggestionHistory.includes(query)) {
        this.suggestionHistory.unshift(query);
        this.suggestionHistory = this.suggestionHistory.slice(0, 10);
        localStorage.setItem('search_history', JSON.stringify(this.suggestionHistory));
      }
    }

    loadHistory() {
      try {
        return JSON.parse(localStorage.getItem('search_history') || '[]');
      } catch {
        return [];
      }
    }
  }

  // ========== 2. 手風琴進階選項 ==========
  class AccordionManager {
    constructor() {
      this.toggle = document.getElementById('advancedOptionsToggle');
      this.content = document.getElementById('advancedOptionsContent');
      this.init();
    }

    init() {
      if (!this.toggle || !this.content) return;
      this.toggle.addEventListener('click', () => this.toggleAccordion());
    }

    toggleAccordion() {
      const isExpanded = this.content.classList.contains('expanded');

      if (isExpanded) {
        this.content.classList.remove('expanded');
        this.content.classList.add('collapsed');
        this.toggle.classList.remove('active');
      } else {
        this.content.classList.remove('collapsed');
        this.content.classList.add('expanded');
        this.toggle.classList.add('active');
      }
    }
  }

  // ========== 3. 進度管理器（真實進度版）==========
  class ProgressManager {
    constructor() {
      this.indicator = document.getElementById('progressIndicator');
      this.bar = document.getElementById('progressBar');
      this.text = document.getElementById('progressText');
      this.details = document.getElementById('progressDetails');
    }

    start() {
      if (!this.indicator) return;
      this.indicator.classList.remove('hidden');
      this.updateProgress(0, '準備中...', '正在初始化研究流程...');
    }

    /**
     * 更新真實進度
     * @param {number} percent - 百分比 (0-100)
     * @param {string} phase - 階段名稱
     * @param {string} message - 詳細訊息
     */
    updateProgress(percent, phase, message) {
      if (this.bar) {
        this.bar.style.width = Math.min(100, Math.max(0, percent)) + '%';
      }
      if (this.text) {
        this.text.textContent = phase || '研究進行中...';
      }
      if (this.details) {
        this.details.textContent = message || '';
      }
    }

    complete() {
      this.updateProgress(100, '完成', '研究報告已生成');
      setTimeout(() => {
        if (this.indicator) {
          this.indicator.classList.add('hidden');
        }
        this.reset();
      }, 1500);
    }

    stop() {
      if (this.indicator) {
        this.indicator.classList.add('hidden');
      }
      this.reset();
    }

    reset() {
      if (this.bar) this.bar.style.width = '0%';
    }
  }

  // ========== 4. 視圖切換管理 ==========
  class ViewManager {
    constructor() {
      this.viewButtons = document.querySelectorAll('.view-btn');
      this.resultsContainer = document.getElementById('resultsContainer');
      this.currentView = 'detailed';
      this.init();
    }

    init() {
      this.viewButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
          const view = e.currentTarget.dataset.view;
          this.switchView(view);
        });
      });
    }

    switchView(view) {
      this.viewButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
      });

      if (this.resultsContainer) {
        this.resultsContainer.className = `results-container view-${view}`;
      }
      this.currentView = view;
    }
  }

  // ========== 5. 研究紀錄管理 ==========
  class ResearchHistoryManager {
    constructor() {
      this.storageKey = 'research_history';
      this.historyList = document.getElementById('researchHistoryList');
      this.clearBtn = document.getElementById('clearHistoryBtn');
      this.history = this.loadHistory();
      this.init();
    }

    init() {
      this.renderHistory();
      if (this.clearBtn) {
        this.clearBtn.addEventListener('click', () => this.clearAll());
      }
    }

    loadHistory() {
      try {
        return JSON.parse(localStorage.getItem(this.storageKey) || '[]');
      } catch {
        return [];
      }
    }

    saveHistory() {
      localStorage.setItem(this.storageKey, JSON.stringify(this.history));
    }

    addItem(query, result) {
      const item = {
        id: Date.now(),
        query: query,
        timestamp: new Date().toISOString(),
        summary: result.substring(0, 100) + '...',
        fullResult: result
      };

      this.history.unshift(item);
      this.history = this.history.slice(0, 50);
      this.saveHistory();
      this.renderHistory();
    }

    renderHistory() {
      if (!this.historyList) return;

      this.historyList.innerHTML = '';

      if (this.history.length === 0) {
        this.historyList.innerHTML = `
          <div class="empty-state" style="padding: 20px;">
            <p style="font-size: 0.9rem; color: var(--text-secondary);">
              尚無研究紀錄
            </p>
          </div>
        `;
        return;
      }

      this.history.forEach(item => {
        const li = document.createElement('li');
        li.className = 'history-item';

        const date = new Date(item.timestamp);
        const timeStr = this.formatTimeAgo(date);

        li.innerHTML = `
          <div class="history-title">
            <i class="fas fa-file-alt"></i>
            <span>${escapeHtml(item.query)}</span>
          </div>
          <div class="history-meta">
            <span>${timeStr}</span>
            <div class="history-actions">
              <button class="history-action-btn" data-action="reload" title="重新執行">
                <i class="fas fa-redo"></i>
              </button>
              <button class="history-action-btn" data-action="delete" title="刪除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
        `;

        li.querySelector('[data-action="reload"]').addEventListener('click', (e) => {
          e.stopPropagation();
          const input = document.getElementById('researchInput');
          if (input) {
            input.value = item.query;
            const startBtn = document.getElementById('startResearchBtn');
            if (startBtn) startBtn.click();
          }
        });

        li.querySelector('[data-action="delete"]').addEventListener('click', (e) => {
          e.stopPropagation();
          this.deleteItem(item.id);
        });

        li.addEventListener('click', () => {
          this.loadResult(item);
        });

        this.historyList.appendChild(li);
      });
    }

    formatTimeAgo(date) {
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return '剛才';
      if (diffMins < 60) return `${diffMins} 分鐘前`;
      if (diffHours < 24) return `${diffHours} 小時前`;
      if (diffDays < 7) return `${diffDays} 天前`;
      return date.toLocaleDateString('zh-TW');
    }

    deleteItem(id) {
      this.history = this.history.filter(item => item.id !== id);
      this.saveHistory();
      this.renderHistory();
    }

    clearAll() {
      if (confirm('確定要清除所有研究紀錄嗎？')) {
        this.history = [];
        this.saveHistory();
        this.renderHistory();
      }
    }

    loadResult(item) {
      const resultsContainer = document.getElementById('resultsContainer');
      const emptyState = document.getElementById('emptyState');

      if (resultsContainer) {
        // ✅ 直接使用原始 HTML（已包含後端生成的完整結構）
        resultsContainer.innerHTML = item.fullResult;
        resultsContainer.scrollTop = 0;
      }

      if (emptyState) {
        emptyState.classList.add('hidden');
      }
    }
  }

  // ========== 6. 匯出功能 ==========
  class ExportManager {
    constructor() {
      this.exportBtn = document.getElementById('exportResultsBtn');
      this.init();
    }

    init() {
      if (this.exportBtn) {
        this.exportBtn.addEventListener('click', () => this.showExportMenu());
      }
    }

    showExportMenu() {
      const menu = document.createElement('div');
      menu.className = 'export-menu';
      menu.innerHTML = `
        <div class="export-menu-content">
          <h4>選擇匯出格式</h4>
          <button class="export-option" data-format="pdf">
            <i class="fas fa-file-pdf"></i> PDF 格式
          </button>
          <button class="export-option" data-format="markdown">
            <i class="fas fa-file-code"></i> Markdown
          </button>
          <button class="export-option" data-format="json">
            <i class="fas fa-file-code"></i> JSON 資料
          </button>
          <button class="export-option" data-format="txt">
            <i class="fas fa-file-alt"></i> 純文字
          </button>
        </div>
      `;

      const style = document.createElement('style');
      style.textContent = `
        .export-menu {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10000;
          animation: fadeIn 0.2s ease;
        }
        .export-menu-content {
          background: var(--bg-secondary);
          border: 1px solid var(--border-color);
          border-radius: 16px;
          padding: 30px;
          min-width: 300px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        .export-menu-content h4 {
          color: var(--accent-purple);
          margin: 0 0 20px 0;
          font-size: 1.2rem;
        }
        .export-option {
          width: 100%;
          background: var(--bg-tertiary);
          border: 1px solid var(--border-color);
          color: var(--text-primary);
          padding: 14px 20px;
          margin: 10px 0;
          border-radius: 8px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 1rem;
          transition: all 0.2s;
        }
        .export-option:hover {
          background: var(--bg-primary);
          border-color: var(--accent-purple);
          transform: translateX(4px);
        }
        .export-option i {
          color: var(--accent-pink);
          font-size: 1.2rem;
        }
      `;
      document.head.appendChild(style);

      document.body.appendChild(menu);

      menu.addEventListener('click', (e) => {
        if (e.target === menu) {
          menu.remove();
        }
      });

      menu.querySelectorAll('.export-option').forEach(btn => {
        btn.addEventListener('click', () => {
          const format = btn.dataset.format;
          this.exportData(format);
          menu.remove();
        });
      });
    }

    exportData(format) {
      const resultsContainer = document.getElementById('resultsContainer');
      const content = resultsContainer ? resultsContainer.innerText || '' : '';
      const input = document.getElementById('researchInput');
      const query = input ? input.value : '未命名研究';
      const timestamp = new Date().toISOString().split('T')[0];

      let data, filename, mimeType;

      switch (format) {
        case 'pdf':
          showToast('PDF 匯出功能目前尚無法使用 (´;ω;`)', 'warning');
          return;

        case 'markdown':
          data = this.convertToMarkdown(query, content);
          filename = `research_${timestamp}.md`;
          mimeType = 'text/markdown';
          break;

        case 'json':
          data = JSON.stringify({
            query: query,
            timestamp: new Date().toISOString(),
            results: content
          }, null, 2);
          filename = `research_${timestamp}.json`;
          mimeType = 'application/json';
          break;

        case 'txt':
          data = `研究主題: ${query}\n\n生成時間: ${new Date().toLocaleString('zh-TW')}\n\n${content}`;
          filename = `research_${timestamp}.txt`;
          mimeType = 'text/plain';
          break;
      }

      this.downloadFile(data, filename, mimeType);
    }

    convertToMarkdown(query, content) {
      return `# ${query}

**生成時間:** ${new Date().toLocaleString('zh-TW')}

---

${content}
`;
    }

    downloadFile(data, filename, mimeType) {
      const blob = new Blob([data], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }

  // ========== 7. 範例查詢按鈕 ==========
  function initExampleQueries() {
    document.querySelectorAll('.example-query-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const query = btn.dataset.query;
        const input = document.getElementById('researchInput');
        const startBtn = document.getElementById('startResearchBtn');

        if (input) input.value = query;
        if (startBtn) startBtn.click();
      });
    });
  }

  // ========== 研究模式管理器（連接後端 API） ==========
  class ResearchManager {
    constructor() {
      this.viewChat = document.getElementById('chat-view');
      this.viewResearch = document.getElementById('research-view');
      this.navChat = document.getElementById('nav-chat');
      this.navResearch = document.getElementById('nav-research');
      this.input = document.getElementById('researchInput');
      this.btn = document.getElementById('startResearchBtn');
      this.resultsContainer = document.getElementById('resultsContainer');
      this.emptyState = document.getElementById('emptyState');
      this.isResearching = false;

      this.initResearchEvents();
    }

    initNavigation() {
      this.navChat?.addEventListener('click', (e) => {
        e.preventDefault();

        // 研究中時詢問是否要切換
        if (AppState.isResearching) {
          if (!confirm('月讀醬正在進行研究中，確定要切換嗎？\n（研究會在背景繼續進行）')) {
            return;
          }
        }

        this.switchView('chat');
      });

      this.navResearch?.addEventListener('click', (e) => {
        e.preventDefault();

        // 聊天等待中時詢問
        if (AppState.isChatting) {
          if (!confirm('正在等待月讀醬的回覆，確定要切換嗎？')) {
            return;
          }
        }

        this.switchView('research');
      });
    }

    switchView(viewName) {
      if (viewName === 'chat') {
        this.viewChat.classList.remove('hidden');
        this.viewChat.classList.add('active');
        this.viewChat.style.display = 'flex';

        this.viewResearch.classList.add('hidden');
        this.viewResearch.classList.remove('active');
        this.viewResearch.style.display = 'none';

        this.navChat.classList.add('active');
        this.navResearch.classList.remove('active');
      } else {
        this.viewChat.classList.add('hidden');
        this.viewChat.classList.remove('active');
        this.viewChat.style.display = 'none';

        this.viewResearch.classList.remove('hidden');
        this.viewResearch.classList.add('active');
        this.viewResearch.style.display = 'flex';

        this.navChat.classList.remove('active');
        this.navResearch.classList.add('active');
      }
    }

    initResearchEvents() {
      this.btn?.addEventListener('click', () => this.performResearch());
      this.input?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') this.performResearch();
      });
    }

    async performResearch() {
      const query = this.input?.value.trim();
      if (!query) {
        showToast('請先輸入研究主題喔 (´;ω;`)', 'warning');
        return;
      }

      if (AppState.isBusy()) {
        showToast('${AppState.getBusyReason()}，請稍等一下喔 (´;ω;`)', 'warning');
        return;
      }

      AppState.isResearching = true;

      if (this.emptyState) {
        this.emptyState.classList.add('hidden');
      }

      this.disableControls();
      const progressMgr = window.researcherManagers?.progressManager;
      progressMgr?.start();

      this.showLoading(query);
      try {
        // ✅ 步驟 1：啟動研究任務，拿到 job_id
        console.log('[Research] 正在啟動研究任務...');
        const startResp = await fetch('/research/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic: query, max_results: 15 })
        });

        if (!startResp.ok) {
          throw new Error(`HTTP ${startResp.status}: ${startResp.statusText}`);
        }

        const startData = await startResp.json();

        // =================== 修改開始 ===================
        // 處理後端回傳 HTTP 200 但 success: false 的情況 (例如: 缺少 API Key 且無本地庫)
        if (startData.success === false) {
          // 使用後端傳來的具體錯誤訊息 (startData.error)
          throw new Error(startData.error || '無法啟動任務');
        }
        // =================== 修改結束 ===================

        if (!startData.job_id) {
          throw new Error('無法啟動研究任務：未返回 job_id');
        }

        const jobId = startData.job_id;
        console.log(`[Research] 已啟動任務：${jobId}`);

        // ✅ 步驟 2：開始輪詢進度
        await this.pollProgress(jobId, query, progressMgr);

      } catch (error) {
        console.error('[Research] 錯誤:', error);
        // 這裡會顯示我們後端傳來的白話文錯誤訊息
        this.showError(error.message || '網路連接失敗，請檢查網路狀態 (´;ω;`)');

        AppState.isResearching = false;
        this.enableControls();
        progressMgr?.stop();
      }
    }

    /**
     * 輪詢研究進度
     * @param {string} jobId - 任務 ID
     * @param {string} query - 研究主題
     * @param {ProgressManager} progressMgr - 進度管理器
     */
    async pollProgress(jobId, query, progressMgr) {
      return new Promise((resolve, reject) => {
        let pollCount = 0;
        const maxPolls = 1200; // 20 分鐘

        const pollTimer = setInterval(async () => {
          pollCount++;

          if (pollCount > maxPolls) {
            clearInterval(pollTimer);
            reject(new Error('研究任務超時（超過 20 分鐘）'));
            return;
          }

          try {
            const resp = await fetch(`/research/progress/${jobId}`);

            if (!resp.ok) {
              console.warn(`[Progress] HTTP ${resp.status}`);
              return;
            }

            const progress = await resp.json();

            if (progress.status === 'not_found') {
              clearInterval(pollTimer);
              reject(new Error('查無此研究任務'));
              return;
            }

            const total = progress.total || 1;
            const current = progress.current || 0;
            const percent = Math.round((current / total) * 100);

            progressMgr?.updateProgress(
              percent,
              progress.phase || '研究中',
              progress.message || `正在處理 ${current}/${total} 個項目...`
            );

            console.log(`[Progress] ${percent}% - ${progress.phase}: ${progress.message}`);

            if (progress.status === "completed") {
              clearInterval(pollTimer);
              console.log("✅ Progress: 已完成！");

              // ========== 強化 Debug ==========
              console.log("[Debug] 完整 progress 物件:", JSON.stringify(progress, null, 2));
              console.log("[Debug] result_html 類型:", typeof progress.result_html);
              console.log("[Debug] result_html 長度:", progress.result_html ? progress.result_html.length : 0);
              console.log("[Debug] result_html 前 500 字:", progress.result_html ? progress.result_html.substring(0, 500) : "(空)");

              // 統計處理
              let stats = progress.stats;
              if (!stats) {
                console.warn("Progress 沒有 stats，使用 result_html 構建統計");
                const wordCount = progress.result_html ? progress.result_html.length : 0;
                stats = {
                  successRate: percent,
                  successItems: current,
                  totalItems: total,
                  wordCount: wordCount
                };
              }

              // ========== 關鍵修正 ==========
              // 檢查 result_html 是否真的有內容（不只是存在，還要有實際文字）
              const hasContent = progress.result_html &&
                progress.result_html.trim().length > 0;

              if (hasContent) {
                console.log("✅ 有內容，準備渲染...");
                this.showResults({
                  success: true,
                  html: progress.result_html,
                  stats: stats
                });

                // 歷史記錄
                const historyMgr = window.researcherManagers?.historyManager;
                historyMgr?.addItem(query, progress.result_html);

                const searchMgr = window.researcherManagers?.searchSuggestion;
                searchMgr?.saveToHistory(query);

                showToast("研究完成！✨", "success");
              } else {
                console.error("❌ result_html 是空的或無效:", progress);
                console.log("[Debug] 檢查後端是否正確生成內容");

                // 顯示更詳細的錯誤訊息
                this.showError(
                  progress.result_html === null
                    ? "後端未回傳研究報告內容 (result_html 為 null)"
                    : progress.result_html === undefined
                      ? "後端未回傳研究報告內容 (result_html 未定義)"
                      : "後端回傳的研究報告內容為空"
                );
              }

              progressMgr?.complete();
              AppState.isResearching = false;
              this.enableControls();
              resolve();
            }
            else if (progress.status === 'failed') {
              clearInterval(pollTimer);

              const errorMsg = progress.error || '研究過程發生未知錯誤';
              console.error('[Progress] 任務失敗:', errorMsg);
              this.showError(errorMsg);

              progressMgr?.stop();
              AppState.isResearching = false;
              this.enableControls();
              reject(new Error(errorMsg));
            }

          } catch (err) {
            console.error('[Progress] 查詢進度失敗:', err);
          }
        }, 1000);
      });
    }

    // 顯示載入中狀態
    showLoading(query) {
      if (this.resultsContainer) {
        this.resultsContainer.innerHTML = `
          <div class="loading-state">
            <div class="loading-animation">
              <div class="loading-spinner"></div>
              <div class="loading-text">
                <h3>月讀醬正在努力研究中～</h3>
                <p>主題：${escapeHtml(query)}</p>
                <p class="loading-hint">這可能需要一些時間，請耐心等待喔 ✨</p>
              </div>
            </div>
          </div>
        `;
      }
    }
    // 顯示研究結果
    showResults(data) {
      if (!this.resultsContainer) return;

      const stats = data.stats || {};
      const successRate = stats.successRate ? stats.successRate // 若是字串則直接用
        : (typeof stats.successRate === 'number' ? stats.successRate.toFixed(1) : "0.0");
      const wordCount = stats.wordCount || 0;
      const successItems = stats.successItems || 0;
      const totalItems = stats.totalItems || 0;

      // 1. 統計區塊
      const statsHtml = `
          <div class="research-stats">
            <div class="stat-item">
              <i class="fas fa-check-circle"></i>
              <span>${successRate}</span>
            </div>
            <div class="stat-item">
              <i class="fas fa-file-alt"></i>
              <span>${wordCount} 字</span>
            </div>
            <div class="stat-item">
              <i class="fas fa-list"></i>
              <span>${successItems}/${totalItems}</span>
            </div>
          </div>
        `;

      // 2. 修正：直接使用後端生成的 HTML
      // 後端 (research_service.py) 已經生成了完整的 HTML 結構 (<div class="report-section">...)
      const bodyHtml = data.html || "";

      // 3. 渲染
      this.resultsContainer.innerHTML = statsHtml + bodyHtml;
      this.resultsContainer.scrollTop = 0;
    }

    // 顯示錯誤訊息
    showError(message) {
      if (this.resultsContainer) {
        this.resultsContainer.innerHTML = `
          <div class="error-state">
            <div class="error-icon">
              <i class="fas fa-exclamation-triangle"></i>
            </div>
            <h3>哎呀～看起來出了點問題 ∑(￣□￣;)</h3>
            <p>${escapeHtml(message)}</p>
            <button class="retry-btn" onclick="window.app.research.performResearch()">
              <i class="fas fa-redo"></i> 重試一次
            </button>
          </div>
        `;
      }
    }

    // 新增：禁用控制項
    disableControls() {
      if (this.btn) {
        this.btn.disabled = true;
        this.btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 研究中...';
      }
      if (this.input) {
        this.input.disabled = true;
      }
      document.querySelectorAll('.nav-center a').forEach(link => {
        link.classList.add('nav-busy');
      });
    }

    // 新增：啟用控制項
    enableControls() {
      if (this.btn) {
        this.btn.disabled = false;
        this.btn.innerHTML = '<i class="fas fa-search"></i> 開始研究';
      }
      if (this.input) {
        this.input.disabled = false;
      }
      document.querySelectorAll('.nav-center a').forEach(link => {
        link.classList.remove('nav-busy');
      });
    }
  }

  // ========== 檔案管理 ==========
  class FileManager {
    constructor() {
      this.storageKey = 'tsukuyomi_files';
      this.filePanel = document.getElementById('filePanel');
      this.toggleBtn = document.getElementById('toggleFilePanel');
      this.closeBtn = document.querySelector('.close-panel-btn');
      this.fileInput = document.getElementById('fileUpload');
      this.fileList = document.querySelector('.file-list');
      this.initEventListeners();
      this.renderFiles();
    }

    initEventListeners() {
      if (this.toggleBtn) {
        this.toggleBtn.addEventListener('click', () => {
          this.filePanel.classList.toggle('collapsed');
        });
      }
      if (this.closeBtn) {
        this.closeBtn.addEventListener('click', () => {
          this.filePanel.classList.add('collapsed');
        });
      }
      if (this.fileInput) {
        this.fileInput.addEventListener('change', (e) => {
          this.handleFileUpload(e);
        });
      }
    }

    loadFiles() {
      try {
        return JSON.parse(localStorage.getItem(this.storageKey)) || [];
      } catch {
        return [];
      }
    }

    saveFiles(files) {
      localStorage.setItem(this.storageKey, JSON.stringify(files));
    }

    handleFileUpload(e) {
      const files = this.loadFiles();
      const maxSize = 10 * 1024 * 1024;
      for (let file of e.target.files) {
        if (file.size > maxSize) {
          alert(`檔案 ${file.name} 超過 10MB 限制`);
          continue;
        }
        files.push({
          name: file.name,
          size: file.size,
          date: new Date().toISOString()
        });
      }
      this.saveFiles(files);
      this.renderFiles();
      this.fileInput.value = '';
    }

    renderFiles() {
      if (!this.fileList) return;
      const files = this.loadFiles();
      this.fileList.innerHTML = '';
      files.forEach((file, idx) => {
        const li = document.createElement('li');
        li.className = 'file-item';
        const icon = document.createElement('i');
        icon.className = 'fa fa-file';
        icon.style.marginRight = '8px';
        icon.style.color = '#ae8ddd';
        const name = document.createElement('span');
        name.className = 'file-name';
        name.textContent = file.name;
        name.title = file.name;
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'delete-file';
        deleteBtn.title = '刪除';
        deleteBtn.innerHTML = '<i class="fa fa-trash"></i>';
        deleteBtn.addEventListener('click', () => {
          const updated = files.filter((_, i) => i !== idx);
          this.saveFiles(updated);
          this.renderFiles();
        });
        li.appendChild(icon);
        li.appendChild(name);
        li.appendChild(deleteBtn);
        this.fileList.appendChild(li);
      });
    }
  }

  // ========== UI 控制 ==========
  class UIController {
    constructor() {
      this.initTabs();
      this.initExpandToggle();
      this.initIntimacyAlignment();
      this.initTermsModal();
    }

    initTabs() {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
          document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          this.classList.add('active');

          // 隱藏所有側邊欄內容
          document.getElementById('sidebar-chat').style.display = 'none';
          document.getElementById('sidebar-file').style.display = 'none';
          const researchHistory = document.getElementById('sidebar-research-history');
          if (researchHistory) researchHistory.style.display = 'none';

          // 顯示對應的側邊欄內容
          if (this.dataset.tab === 'chat') {
            document.getElementById('sidebar-chat').style.display = '';
          } else if (this.dataset.tab === 'file') {
            document.getElementById('sidebar-file').style.display = '';
          } else if (this.dataset.tab === 'research-history') {
            if (researchHistory) researchHistory.style.display = '';
          }
        });
      });
    }

    initExpandToggle() {
      // 1. 取得關鍵元素
      const btn = document.querySelector('.edge-toggle-btn'); // 建議用 class 抓取，比較通用
      const container = document.querySelector('.container');
      const btnIcon = btn ? btn.querySelector('i') : null;

      if (!btn || !container || !btnIcon) return;

      // 2. 定義狀態更新函數 (View Update)
      const updateState = (isExpanded) => {
        // 切換 Container class (控制 Layout)
        container.classList.toggle('chat-expanded', isExpanded);

        // 更新按鈕狀態 (控制 Icon 與 Tooltip)
        if (isExpanded) {
          btn.classList.add('collapsed'); // 按鈕樣式變化 (例如旋轉)
          btn.title = "展開Live2D";
          // 讓 Icon 旋轉 180度，而不是直接換 Icon，動畫較順暢
          btnIcon.className = 'fa fa-chevron-right';
        } else {
          btn.classList.remove('collapsed');
          btn.title = "收合Live2D";
          btnIcon.className = 'fa fa-chevron-left';
        }

        // 儲存偏好
        localStorage.setItem('chat_expanded', isExpanded);

        // 觸發 Live2D 重繪 (動畫結束後執行)
        // 400ms 是配合 CSS transition 時間
        setTimeout(() => {
          if (window.live2dController) {
            window.live2dController.handleResize();
          }
        }, 450);
      };

      // 3. 初始化狀態 (讀取 localStorage)
      const savedState = localStorage.getItem('chat_expanded') === 'true';
      updateState(savedState); // 應用上次的狀態

      // 4. 綁定點擊事件
      btn.addEventListener('click', () => {
        // 檢查當前是否已經是 expanded 狀態
        const isCurrentlyExpanded = container.classList.contains('chat-expanded');
        // 切換到相反狀態
        updateState(!isCurrentlyExpanded);
      });
    }

    initIntimacyAlignment() {
      const alignIntimacy = () => {
        const live2dPanel = document.querySelector('.live2d-panel');
        const intimacy = document.getElementById('intimacy-display');
        if (!live2dPanel || !intimacy) return;
        const rect = live2dPanel.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const width = intimacy.offsetWidth;
        intimacy.style.left = `${centerX - width / 2}px`;
      };
      window.addEventListener('DOMContentLoaded', alignIntimacy);
      window.addEventListener('resize', alignIntimacy);
      setTimeout(alignIntimacy, 100);
    }

    initTermsModal() {
      const modal = document.getElementById('termsModal');
      const aboutBtn = document.getElementById('aboutBtn');
      const closeBtn = document.getElementById('closeTermsBtn');
      if (aboutBtn) aboutBtn.addEventListener('click', () => { modal.style.display = 'block'; });
      if (closeBtn) closeBtn.addEventListener('click', () => { modal.style.display = 'none'; });
      if (modal) {
        modal.addEventListener('click', (e) => {
          if (e.target === modal) modal.style.display = 'none';
        });
      }
    }
  }

  // ========== 應用初始化 ==========
  document.addEventListener('DOMContentLoaded', function () {
    console.log('🚀 開始初始化應用...');

    // 初始化核心功能
    const live2dController = new Live2DController();
    const chatManager = new ChatManager();
    const fileManager = new FileManager();
    const uiController = new UIController();
    const researchManager = new ResearchManager();

    // 初始化 Researcher 改善功能
    const searchSuggestion = new SearchSuggestionManager();
    const accordion = new AccordionManager();
    const progressManager = new ProgressManager();
    const viewManager = new ViewManager();
    const historyManager = new ResearchHistoryManager();
    const exportManager = new ExportManager();

    initExampleQueries();

    live2dController.init();

    // Live2D 動作控制
    document.querySelectorAll('#controls .control-item').forEach(item => {
      const motionName = item.dataset.motion;
      if (motionName) {
        item.addEventListener('click', () => {
          live2dController.playMotion(motionName);
        });
      }
    });

    // 記憶與語音控制
    document.getElementById('replayAudio')?.addEventListener('click', () => {
      live2dController.replayAudio();
    });
    document.getElementById('clearSession')?.addEventListener('click', () => {
      chatManager.clearSession();
    });
    document.getElementById('clearAllMemory')?.addEventListener('click', () => {
      chatManager.clearAllMemory();
    });
    // Live2D 點擊互動
    const live2dArea = document.getElementById('live2d-area');
    if (live2dArea) {
      live2dArea.addEventListener('click', function () {
        if (window.live2dModel && typeof window.app?.live2d?.playMotion === 'function') {
          window.app.live2d.playMotion('Tap');
        }
      });
    }

    // 暴露給全域使用
    window.app = {
      live2d: live2dController,
      chat: chatManager,
      file: fileManager,
      ui: uiController,
      research: researchManager
    };

    window.researcherManagers = {
      searchSuggestion,
      accordion,
      progressManager,
      viewManager,
      historyManager,
      exportManager
    };

    updateIntimacyDisplay();
    console.log('✅ 所有功能已成功載入');
  });
})();

// =================== 視圖切換功能（單一來源版） ===================
(function () {
  'use strict';

  function setNavActive(viewName) {
    const navChat = document.getElementById('nav-chat');
    const navResearch = document.getElementById('nav-research');

    navChat?.classList.toggle('active', viewName === 'chat');
    navResearch?.classList.toggle('active', viewName === 'research');
  }

  // 視圖切換函數（帶記憶 + 忙碌確認 + 導覽列 active）
  window.switchMainView = function (viewName) {
    // 忙碌時的切換確認（統一入口）
    if (viewName === 'chat' && window.AppState?.isResearching) {
      if (!confirm('月讀醬正在進行研究中，確定要切換嗎？\n（研究會在背景繼續進行）')) return;
    }
    if (viewName === 'research' && window.AppState?.isChatting) {
      if (!confirm('正在等待月讀醬的回覆，確定要切換嗎？')) return;
    }

    // 記住上一個視圖（不記 settings）
    const currentView = localStorage.getItem('currentView');
    if (currentView && currentView !== 'settings') {
      localStorage.setItem('previousView', currentView);
    }

    // 隱藏所有視圖
    document.querySelectorAll('.view-section').forEach(section => {
      section.style.display = 'none';
      section.classList.remove('active');
      section.classList.add('hidden');
    });

    // 顯示指定視圖
    const targetView = document.getElementById(`${viewName}-view`);
    if (!targetView) {
      console.error('找不到視圖:', `${viewName}-view`);
      return;
    }
    targetView.style.display = 'flex';
    targetView.classList.add('active');
    targetView.classList.remove('hidden');

    // 更新導覽列 active
    setNavActive(viewName);

    // 儲存當前視圖
    localStorage.setItem('currentView', viewName);
  };

  document.addEventListener('DOMContentLoaded', function () {
    // 設定按鈕
    document.getElementById('settingsBtn')?.addEventListener('click', (e) => {
      e.preventDefault();
      switchMainView('settings');
    });

    // 返回按鈕（回到 previousView，預設 chat）
    document.getElementById('backToChatBtn')?.addEventListener('click', (e) => {
      e.preventDefault();
      const previousView = localStorage.getItem('previousView') || 'chat';
      switchMainView(previousView);
    });

    // 導覽列（只在這裡綁一次）
    document.getElementById('nav-chat')?.addEventListener('click', (e) => {
      e.preventDefault();
      switchMainView('chat');
    });

    document.getElementById('nav-research')?.addEventListener('click', (e) => {
      e.preventDefault();
      switchMainView('research');
    });

    // 初始化：若上次是 settings，強制回 chat
    const savedView = localStorage.getItem('currentView') || 'chat';
    const viewToShow = savedView === 'settings' ? 'chat' : savedView;
    switchMainView(viewToShow);
  });
})();

// =================== 設定頁面功能 ===================
(function () {
  'use strict';

  const SETTINGS_KEY = 'tsukuyomi_settings';

  // 預設設定
  const defaultSettings = {
    theme: 'dark',
    fontSize: 16,
    tavilyApiKey: '',
    smartLLM: 'ministral-3:3b',
    smallLLM: 'gemma3:4b'
  };

  // 修改 loadSettings 函數
  async function loadSettings() {
    try {
      // 1. 快速從 localStorage 載入
      const saved = localStorage.getItem(SETTINGS_KEY);
      if (saved) {
        try {
          const localSettings = { ...defaultSettings, ...JSON.parse(saved) };
          console.log('✅ 從 localStorage 載入:', localSettings);
          return localSettings;
        } catch (e) {
          console.warn('⚠️ localStorage 解析失敗:', e);
        }
      }

      // 2. 從伺服器載入
      try {
        console.log('🔄 從伺服器載入設定...');
        const response = await fetch('/api/settings', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
          const serverSettings = await response.json();
          console.log('✅ 從伺服器載入:', serverSettings);

          // 驗證返回的數據有效性
          if (serverSettings && typeof serverSettings === 'object') {
            // 確保有所有必要字段
            const validSettings = {
              theme: serverSettings.theme || 'dark',
              fontSize: serverSettings.fontSize || 16,
              tavilyApiKey: serverSettings.tavilyApiKey || '',
              smartLLM: serverSettings.smartLLM || 'ministral-3:3b',
              smallLLM: serverSettings.smallLLM || 'gemma3:4b'
            };

            // 保存到 localStorage 作為備份
            localStorage.setItem(SETTINGS_KEY, JSON.stringify(validSettings));
            return validSettings;
          }
        } else {
          console.warn('⚠️ 伺服器回應非 OK:', response.status);
        }
      } catch (networkError) {
        console.warn('⚠️ 網路錯誤:', networkError);
      }

      // 3. 返回預設值
      console.log('📋 使用預設設定');
      return { ...defaultSettings };

    } catch (e) {
      console.error('❌ loadSettings 出錯:', e);
      return { ...defaultSettings };
    }
  }

  // 修改 saveSettings 函數
  async function saveSettings(settings) {
    try {
      // 驗證 settings 有效性
      if (!settings || typeof settings !== 'object') {
        console.error('❌ 無效的設定對象');
        return false;
      }

      // 1. 立刻儲存到 localStorage
      try {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
        console.log('✅ 已儲存到 localStorage');
      } catch (storageError) {
        console.warn('⚠️ localStorage 儲存失敗:', storageError);
        // 繼續執行，不中止
      }

      // 2. 非同步上傳到伺服器
      setTimeout(() => {
        fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ settings })
        })
          .then(res => {
            if (!res.ok) {
              console.warn(`⚠️ 伺服器回應 ${res.status}`);
              return;
            }
            return res.json();
          })
          .then(data => {
            console.log('✅ 伺服器已儲存:', data);
          })
          .catch(err => {
            console.warn('⚠️ 伺服器同步失敗（已儲存本地）:', err);
          });
      }, 100);

      return true;

    } catch (e) {
      console.error('❌ saveSettings 出錯:', e);
      return false;
    }
  }

  // 修改測試 API 按鈕
  const testApiBtn = document.getElementById('test-api-btn');
  if (testApiBtn) {
    testApiBtn.addEventListener('click', async () => {
      const apiKey = tavilyApiInput ? tavilyApiInput.value.trim() : settings.tavilyApiKey;

      if (!apiKey) {
        alert('請先輸入 Tavily API Key');
        return;
      }

      testApiBtn.disabled = true;
      testApiBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 驗證中...';

      try {
        const response = await fetch('/api/settings/test-api', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ apiKey })
        });

        const result = await response.json();

        if (result.success) {
          alert('✓ API Key 驗證成功');
        } else {
          alert('✗ ' + result.message);
        }
      } catch (e) {
        alert('✗ 驗證失敗: ' + e.message);
      } finally {
        testApiBtn.disabled = false;
        testApiBtn.innerHTML = '<i class="fa fa-vial"></i> 測試 API';
      }
    });
  }


  // 套用主題
  function applyTheme(theme) {
    if (theme === 'light') {
      document.body.classList.add('light-theme');
      console.log('已切換至亮色主題');
    } else {
      document.body.classList.remove('light-theme');
      console.log('已切換至暗色主題');
    }
  }

  // 套用字體大小
  function applyFontSize(size) {
    const fontSize = parseInt(size, 10) || 16;
    document.documentElement.style.setProperty('--chat-font-size', fontSize + 'px');
    console.log('✅ 字體大小已更新:', fontSize + 'px');
  }

  // 初始化設定頁面
  async function initSettingsPage() {
    console.log('初始化設定頁面...');
    const settings = await loadSettings();

    // 套用已儲存的設定
    applyTheme(settings.theme);
    applyFontSize(settings.fontSize);

    // 主題選擇
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
      themeSelect.value = settings.theme;
      themeSelect.addEventListener('change', (e) => {
        settings.theme = e.target.value;
        applyTheme(settings.theme);
        saveSettings(settings);
        if (window.showToast) {
          showToast('主題已更新', 'success');
        }
      });
      console.log('主題選擇已綁定');
    }

    // 字體大小
    const fontSizeSlider = document.getElementById('font-size-slider');
    const fontSizeValue = document.getElementById('font-size-value');
    if (fontSizeSlider && fontSizeValue) {
      fontSizeSlider.value = settings.fontSize;
      fontSizeValue.textContent = settings.fontSize + 'px';

      fontSizeSlider.addEventListener('input', (e) => {
        const size = parseInt(e.target.value);
        fontSizeValue.textContent = size + 'px';
        applyFontSize(size);
      });

      fontSizeSlider.addEventListener('change', (e) => {
        settings.fontSize = parseInt(e.target.value);
        saveSettings(settings);
      });
      console.log('字體大小滑桿已綁定');
    }

    // Tavily API Key
    const tavilyApiInput = document.getElementById('tavily-api-input');
    if (tavilyApiInput) {
      tavilyApiInput.value = settings.tavilyApiKey;
      tavilyApiInput.addEventListener('blur', (e) => {
        settings.tavilyApiKey = e.target.value.trim();
      });
    }

    // 顯示/隱藏 API Key
    const toggleTavilyBtn = document.getElementById('toggle-tavily');
    if (toggleTavilyBtn && tavilyApiInput) {
      toggleTavilyBtn.addEventListener('click', () => {
        const isPassword = tavilyApiInput.type === 'password';
        tavilyApiInput.type = isPassword ? 'text' : 'password';
        toggleTavilyBtn.innerHTML = isPassword
          ? '<i class="fa fa-eye-slash"></i>'
          : '<i class="fa fa-eye"></i>';
      });
    }

    // Smart LLM
    const smartLLMInput = document.getElementById('smart-llm-input');
    if (smartLLMInput) {
      smartLLMInput.value = settings.smartLLM;
      smartLLMInput.addEventListener('blur', (e) => {
        settings.smartLLM = e.target.value.trim();
      });
    }

    // Small LLM
    const smallLLMInput = document.getElementById('small-llm-input');
    if (smallLLMInput) {
      smallLLMInput.value = settings.smallLLM;
      smallLLMInput.addEventListener('blur', (e) => {
        settings.smallLLM = e.target.value.trim();
      });
    }

    // 儲存設定按鈕
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    if (saveSettingsBtn) {
      saveSettingsBtn.addEventListener('click', () => {
        // 再次確保所有值都已更新
        if (tavilyApiInput) settings.tavilyApiKey = tavilyApiInput.value.trim();
        if (smartLLMInput) settings.smartLLM = smartLLMInput.value.trim();
        if (smallLLMInput) settings.smallLLM = smallLLMInput.value.trim();

        if (saveSettings(settings)) {
          if (window.showToast) {
            showToast('設定已儲存', 'success');
          } else {
            alert('設定已儲存');
          }
          console.log('已儲存設定:', settings);
        } else {
          if (window.showToast) {
            showToast('儲存失敗，請稍後再試', 'error');
          } else {
            alert('儲存失敗');
          }
        }
      });
      console.log('儲存按鈕已綁定');
    }

    // 測試 API 按鈕
    const testApiBtn = document.getElementById('test-api-btn');
    if (testApiBtn) {
      testApiBtn.addEventListener('click', () => {
        const apiKey = tavilyApiInput ? tavilyApiInput.value.trim() : settings.tavilyApiKey;

        if (!apiKey) {
          if (window.showToast) {
            showToast('請先輸入 Tavily API Key', 'warning');
          } else {
            alert('請先輸入 Tavily API Key');
          }
          return;
        }

        // 簡單驗證格式
        if (apiKey.length < 20) {
          if (window.showToast) {
            showToast('API Key 格式可能不正確', 'warning');
          } else {
            alert('API Key 格式可能不正確');
          }
          return;
        }

        testApiBtn.disabled = true;
        testApiBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 驗證中...';

        setTimeout(() => {
          if (window.showToast) {
            showToast('API Key 已儲存，將在實際研究時驗證', 'success');
          } else {
            alert('API Key 已儲存');
          }
          testApiBtn.disabled = false;
          testApiBtn.innerHTML = '<i class="fa fa-vial"></i> 測試 API';
        }, 1000);
      });
      console.log('測試 API 按鈕已綁定');
    }

    console.log('設定頁面初始化完成');
  }

  // 頁面載入後初始化設定
  window.addEventListener('load', () => {
    setTimeout(() => {
      window.initSettingsPage?.();
    }, 300);
  });

  // 暴露設定函數供其他模組使用
  window.getSettings = loadSettings;
  window.saveAppSettings = saveSettings;
  window.initSettingsPage = initSettingsPage;
})();
