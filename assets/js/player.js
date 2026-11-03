// Audio player bar. Beside timed text it also highlights the word being spoken and jumps to clicked words.
(function () {
  var SKIP_SECONDS = 5;

  var bars = document.querySelectorAll('.player');
  var audios = document.querySelectorAll('.player audio');

  function clockText(seconds) {
    var whole = Math.floor(seconds);
    var rest = whole % 60;
    return Math.floor(whole / 60) + ':' + (rest < 10 ? '0' : '') + rest;
  }

  function setUp(bar) {
    var audio = bar.querySelector('audio');
    var playButton = bar.querySelector('.p-play');
    var seek = bar.querySelector('.p-seek');
    var timeLabel = bar.querySelector('.p-time');
    var totalLabel = bar.querySelector('.p-total');
    var speedButtons = bar.querySelectorAll('[data-speed]');
    var loopButton = bar.querySelector('.p-loop');
    var timed = bar.closest('.timed');
    var words = timed ? timed.querySelectorAll('.pw') : [];
    var starts = Array.prototype.map.call(words, function (word) {
      return parseFloat(word.dataset.t);
    });

    var activeWord = null;
    var dragging = false;

    // The last word that has started by this time, or -1 before the first word.
    function wordIndexAt(time) {
      var low = 0;
      var high = starts.length - 1;
      var found = -1;
      while (low <= high) {
        var middle = (low + high) >> 1;
        if (starts[middle] <= time) {
          found = middle;
          low = middle + 1;
        } else {
          high = middle - 1;
        }
      }
      return found;
    }

    function highlight(word) {
      if (word === activeWord) return;
      if (activeWord) activeWord.classList.remove('now');
      activeWord = word;
      if (word) {
        word.classList.add('now');
        if (!audio.paused) word.scrollIntoView({ block: 'nearest' });
      }
    }

    function show() {
      var index = wordIndexAt(audio.currentTime);
      highlight(index >= 0 && !audio.ended ? words[index] : null);
      if (!dragging) seek.value = audio.currentTime;
      timeLabel.textContent = clockText(audio.currentTime);
    }

    function follow() {
      if (audio.paused) return;
      show();
      requestAnimationFrame(follow);
    }

    function play() {
      window.LiveEnglish.stop();
      audio.play().catch(function (error) {
        if (error.name !== 'AbortError') window.console.error(error);
      });
    }

    function moveTo(time) {
      audio.currentTime = Math.max(0, Math.min(time, parseFloat(seek.max)));
      show();
    }

    audio.addEventListener('play', function () {
      audios.forEach(function (other) {
        if (other !== audio) {
          other.pause();
          other.dispatchEvent(new Event('replaced'));
        }
      });
      playButton.classList.add('playing');
      requestAnimationFrame(follow);
    });
    audio.addEventListener('pause', function () { playButton.classList.remove('playing'); });
    audio.addEventListener('replaced', function () { highlight(null); });
    audio.addEventListener('ended', show);
    audio.addEventListener('seeked', show);
    audio.addEventListener('emptied', show);
    audio.addEventListener('durationchange', function () {
      if (isFinite(audio.duration)) {
        seek.max = audio.duration;
        totalLabel.textContent = clockText(audio.duration);
      }
    });

    playButton.addEventListener('click', function () {
      // A playlist's audio has no file until the playlist chooses one.
      if (!audio.getAttribute('src')) bar.dispatchEvent(new Event('needsource'));
      else if (audio.paused) play();
      else audio.pause();
    });

    bar.querySelector('.p-stop').addEventListener('click', function () {
      audio.pause();
      moveTo(0);
      highlight(null);
    });

    if (loopButton) {
      loopButton.addEventListener('click', function () {
        audio.loop = !audio.loop;
        loopButton.setAttribute('aria-pressed', audio.loop ? 'true' : 'false');
      });
    }

    bar.querySelector('.p-back').addEventListener('click', function () {
      moveTo(audio.currentTime - SKIP_SECONDS);
    });

    bar.querySelector('.p-forward').addEventListener('click', function () {
      moveTo(audio.currentTime + SKIP_SECONDS);
    });

    seek.addEventListener('input', function () {
      dragging = true;
      timeLabel.textContent = clockText(parseFloat(seek.value));
    });

    seek.addEventListener('change', function () {
      dragging = false;
      moveTo(parseFloat(seek.value));
    });

    speedButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        var speed = parseFloat(button.dataset.speed);
        audio.defaultPlaybackRate = speed;
        audio.playbackRate = speed;
        speedButtons.forEach(function (other) {
          other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
        });
      });
    });

    if (timed) {
      timed.querySelector('.timed-text').addEventListener('click', function (event) {
        var word = event.target.closest('.pw');
        if (!word) return;
        moveTo(parseFloat(word.dataset.t));
        play();
      });
    }
  }

  bars.forEach(setUp);

  document.addEventListener('tabchange', function () {
    audios.forEach(function (audio) { audio.pause(); });
  });
})();
