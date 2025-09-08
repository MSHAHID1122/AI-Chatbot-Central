// static/i18n_widget.js
(function(){
  const AR_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

  function detectClientLangFromInput(text) {
    if (!text || text.trim().length === 0) return null;
    const arMatches = (text.match(AR_RE) || []).length;
    const latinMatches = (text.match(/[A-Za-z]/g) || []).length;
    if (arMatches >= 2 && arMatches >= latinMatches) return 'ar';
    if (latinMatches >= 2 && latinMatches >= arMatches) return 'en';
    return null;
  }

  window.i18nWidget = {
    setLanguageOnWidget: function(containerEl, lang) {
      if (!containerEl) return;
      if (lang === 'ar') {
        containerEl.classList.add('rtl');
        containerEl.setAttribute('dir', 'rtl');
        containerEl.setAttribute('lang', 'ar');
      } else {
        containerEl.classList.remove('rtl');
        containerEl.setAttribute('dir', 'ltr');
        containerEl.setAttribute('lang', 'en');
      }
    },
    quickDetectAndApply: function(containerEl, inputText, allowPrompt=true) {
      const lang = detectClientLangFromInput(inputText);
      if (lang) {
        this.setLanguageOnWidget(containerEl, lang);
        return lang;
      }
      if (allowPrompt) {
        // optional: show small language toggle if uncertain
        // implement UI prompt as needed
      }
      return null;
    }
  };
})();