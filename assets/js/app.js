// One shared player: every speaker button on the page plays through it.
(function () {
  var HOVER_DELAY = 130;
  var player = new Audio();
  var activeButton = null;
  var hoverTimer = null;
  var hoverBlocked = false;

  var toast = document.querySelector('.toast');

  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    setTimeout(function () { toast.hidden = true; }, 4000);
  }

  function setActive(button) {
    if (activeButton) activeButton.classList.remove('playing');
    activeButton = button;
    if (button) button.classList.add('playing');
  }

  function play(button, fromHover) {
    player.pause();
    setActive(button);
    player.src = button.dataset.src;
    player.play().catch(function (error) {
      setActive(null);
      if (error.name === 'NotAllowedError' && fromHover) {
        // Browsers refuse sound until the first click on the page.
        if (!hoverBlocked) showToast('اضغط مرة واحدة في أي مكان بالصفحة لتفعيل الصوت عند مرور الماوس');
        hoverBlocked = true;
      } else if (error.name !== 'AbortError') {
        showToast('تعذر تشغيل الصوت');
      }
    });
  }

  player.addEventListener('ended', function () { setActive(null); });

  document.addEventListener('click', function (event) {
    hoverBlocked = false;
    var button = event.target.closest('.spk');
    if (button) {
      clearTimeout(hoverTimer);
      play(button);
    }
  });

  document.addEventListener('mouseover', function (event) {
    var button = event.target.closest('.spk');
    if (!button || button.contains(event.relatedTarget)) return;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(function () {
      play(button, true);
    }, HOVER_DELAY);
  });

  document.addEventListener('mouseout', function (event) {
    var button = event.target.closest('.spk');
    if (button && !button.contains(event.relatedTarget)) clearTimeout(hoverTimer);
  });

  function stop() {
    clearTimeout(hoverTimer);
    player.pause();
    setActive(null);
  }

  window.LiveEnglish = {
    play: function (button) { play(button); },
    stop: stop
  };

  // Tabs on word pages. The hash keeps the open tab across reloads and the back button.
  var tabs = document.querySelectorAll('[data-tab]');
  if (!tabs.length) return;

  function openTab() {
    var name = location.hash.slice(1);
    if (!document.querySelector('[data-tab="' + name + '"]')) name = tabs[0].dataset.tab;
    stop();
    tabs.forEach(function (tab) {
      tab.setAttribute('aria-selected', tab.dataset.tab === name ? 'true' : 'false');
    });
    document.querySelectorAll('[data-panel]').forEach(function (panel) {
      panel.hidden = panel.dataset.panel !== name;
    });
    document.dispatchEvent(new CustomEvent('tabchange', { detail: name }));
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () { location.hash = tab.dataset.tab; });
  });
  window.addEventListener('hashchange', openTab);
  openTab();
})();
