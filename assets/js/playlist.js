// Playlist on the audio lessons page: plays the ticked files in order or shuffled.
// The bar's play, seek, skip and speed controls come from player.js; this adds the queue.
(function () {
  var panel = document.querySelector('.playlist');
  if (!panel) return;

  var bar = panel.querySelector('.player');
  var audio = bar.querySelector('audio');
  var summary = panel.querySelector('.playlist-summary');
  var nowLabel = panel.querySelector('.playlist-now');
  var shuffleButton = panel.querySelector('.p-shuffle');
  var repeatButton = panel.querySelector('.p-repeat');
  var picks = Array.prototype.slice.call(document.querySelectorAll('.lesson-pick'));
  var storageKey = 'live-english-playlist:' + location.pathname;

  var REPEAT_MODES = {
    off: { next: 'all', label: 'التكرار: بدون' },
    all: { next: 'one', label: 'التكرار: القائمة كلها' },
    one: { next: 'off', label: 'التكرار: الملف الحالي' }
  };

  var queue = [];
  var position = -1;
  var current = null;
  var shuffleOn = false;
  var repeatMode = 'off';

  function clockText(seconds) {
    var whole = Math.round(seconds);
    var rest = whole % 60;
    return Math.floor(whole / 60) + ':' + (rest < 10 ? '0' : '') + rest;
  }

  function shuffled(list) {
    var copy = list.slice();
    for (var i = copy.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var swap = copy[i];
      copy[i] = copy[j];
      copy[j] = swap;
    }
    return copy;
  }

  function ticked() {
    return picks.filter(function (pick) { return pick.checked; });
  }

  // A new order from the ticks. The playing file stays first in a new shuffle, so nothing repeats early.
  function buildQueue() {
    queue = ticked();
    if (shuffleOn) {
      queue = shuffled(queue);
      var at = queue.indexOf(current);
      if (at > 0) {
        queue.splice(at, 1);
        queue.unshift(current);
      }
    }
    position = queue.indexOf(current);
  }

  // Ticks changed while listening: a shuffled order is kept, with new files added at its end.
  function syncQueue() {
    var chosen = ticked();
    if (shuffleOn) {
      var kept = queue.filter(function (pick) { return pick.checked; });
      var added = chosen.filter(function (pick) { return kept.indexOf(pick) < 0; });
      queue = kept.concat(shuffled(added));
    } else {
      queue = chosen;
    }
    position = queue.indexOf(current);
  }

  function fileCount(count) {
    if (count === 1) return 'ملف واحد';
    if (count === 2) return 'ملفين';
    return count + (count <= 10 ? ' ملفات' : ' ملف');
  }

  function saveTicks() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(ticked().map(function (pick) { return pick.dataset.src; })));
    } catch (error) { /* The playlist still works, it just won't be remembered. */ }
  }

  function restoreTicks() {
    try {
      var saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
      picks.forEach(function (pick) { pick.checked = saved.indexOf(pick.dataset.src) >= 0; });
    } catch (error) { /* Start with nothing ticked. */ }
  }

  function showSummary() {
    var chosen = ticked();
    var seconds = chosen.reduce(function (total, pick) { return total + parseFloat(pick.dataset.seconds); }, 0);
    summary.textContent = chosen.length ? fileCount(chosen.length) + ' · ' + clockText(seconds) : 'علّم على الملفات اللي عايز تسمعها';
    document.querySelectorAll('.pick-section').forEach(function (button) {
      var boxes = button.closest('.lesson-group').querySelectorAll('.lesson-pick');
      var allOn = Array.prototype.every.call(boxes, function (box) { return box.checked; });
      button.textContent = allOn ? 'إلغاء القسم' : 'تحديد القسم';
    });
  }

  function showNow() {
    document.querySelectorAll('.lesson.current').forEach(function (row) { row.classList.remove('current'); });
    if (!current) {
      nowLabel.textContent = '';
      return;
    }
    current.closest('.lesson').classList.add('current');
    nowLabel.textContent = (position >= 0 ? (position + 1) + ' من ' + queue.length + ': ' : '') + current.dataset.title;
  }

  function selectionChanged() {
    saveTicks();
    showSummary();
    syncQueue();
    showNow();
  }

  function playAt(index) {
    position = index;
    current = queue[index];
    audio.src = current.dataset.src;
    audio.loop = repeatMode === 'one';
    showNow();
    window.LiveEnglish.stop();
    audio.play().catch(function (error) {
      if (error.name !== 'AbortError') window.console.error(error);
    });
  }

  function finish() {
    current = null;
    position = -1;
    audio.removeAttribute('src');
    audio.load();
    showNow();
  }

  function start() {
    buildQueue();
    if (!queue.length) {
      nowLabel.textContent = 'علّم على ملف واحد على الأقل الأول';
      return;
    }
    playAt(0);
  }

  function next(fromEnd) {
    if (!queue.length) {
      finish();
    } else if (position + 1 < queue.length) {
      playAt(position + 1);
    } else if (repeatMode === 'all' || !fromEnd) {
      // Each round of a shuffled list gets a new order.
      if (shuffleOn) queue = shuffled(queue);
      playAt(0);
    } else {
      finish();
    }
  }

  function previous() {
    if (queue.length) playAt(position > 0 ? position - 1 : queue.length - 1);
  }

  bar.addEventListener('needsource', start);
  audio.addEventListener('ended', function () { next(true); });
  panel.querySelector('.p-next').addEventListener('click', function () { next(false); });
  panel.querySelector('.p-previous').addEventListener('click', previous);

  shuffleButton.addEventListener('click', function () {
    shuffleOn = !shuffleOn;
    shuffleButton.setAttribute('aria-pressed', shuffleOn ? 'true' : 'false');
    buildQueue();
    showNow();
  });

  repeatButton.addEventListener('click', function () {
    repeatMode = REPEAT_MODES[repeatMode].next;
    repeatButton.dataset.mode = repeatMode;
    repeatButton.title = REPEAT_MODES[repeatMode].label;
    repeatButton.setAttribute('aria-label', REPEAT_MODES[repeatMode].label);
    audio.loop = repeatMode === 'one';
  });

  panel.querySelector('.playlist-picks').addEventListener('click', function (event) {
    var button = event.target.closest('[data-pick]');
    if (!button) return;
    var pick = button.dataset.pick;
    picks.forEach(function (box) {
      if (pick === 'all') box.checked = true;
      else if (pick === 'none') box.checked = false;
      else if (box.dataset.kind === pick) box.checked = true;
    });
    selectionChanged();
  });

  document.addEventListener('click', function (event) {
    var button = event.target.closest('.pick-section');
    if (!button) return;
    var boxes = Array.prototype.slice.call(button.closest('.lesson-group').querySelectorAll('.lesson-pick'));
    var turnOn = !boxes.every(function (box) { return box.checked; });
    boxes.forEach(function (box) { box.checked = turnOn; });
    selectionChanged();
  });

  picks.forEach(function (pick) { pick.addEventListener('change', selectionChanged); });

  restoreTicks();
  showSummary();
})();
