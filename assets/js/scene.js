// Film scene player: plays one stretch of the film, highlights the script and repeats single lines.
(function () {
  var SKIP_SECONDS = 5;

  var grid = document.querySelector('.scene-grid');
  if (!grid) return;

  var video = grid.querySelector('video');
  var bar = grid.querySelector('.player');
  var playButton = bar.querySelector('.p-play');
  var loopButton = bar.querySelector('.p-loop');
  var seek = bar.querySelector('.p-seek');
  var timeLabel = bar.querySelector('.p-time');
  var speedButtons = bar.querySelectorAll('[data-speed]');
  var script = grid.querySelector('.scene-script');
  var words = script.querySelectorAll('.pw');
  var starts = Array.prototype.map.call(words, function (word) {
    return parseFloat(word.dataset.t);
  });

  var sceneStart = parseFloat(grid.dataset.start);
  var sceneEnd = parseFloat(grid.dataset.end);
  var activeWord = null;
  var repeatLine = null;
  var loopScene = false;
  var dragging = false;

  function clockText(value) {
    var whole = Math.floor(Math.max(value, 0));
    var rest = whole % 60;
    return Math.floor(whole / 60) + ':' + (rest < 10 ? '0' : '') + rest;
  }

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
      if (!video.paused) word.scrollIntoView({ block: 'nearest' });
    }
  }

  function moveTo(time) {
    video.currentTime = Math.max(sceneStart, Math.min(time, sceneEnd));
    show();
  }

  // Keeps playback inside the repeated line or the scene.
  function holdInRange() {
    if (repeatLine) {
      var lineStart = parseFloat(repeatLine.dataset.start);
      var lineEnd = parseFloat(repeatLine.dataset.end);
      if (video.currentTime >= lineEnd || video.currentTime < lineStart - 0.5) video.currentTime = lineStart;
    } else if (video.currentTime >= sceneEnd) {
      if (loopScene) {
        video.currentTime = sceneStart;
      } else {
        video.pause();
        video.currentTime = sceneEnd;
      }
    }
  }

  function show() {
    var time = video.currentTime;
    var index = wordIndexAt(time);
    highlight(index >= 0 && time < sceneEnd ? words[index] : null);
    if (!dragging) seek.value = Math.max(time - sceneStart, 0);
    timeLabel.textContent = clockText(time - sceneStart);
  }

  function follow() {
    if (video.paused) return;
    holdInRange();
    show();
    requestAnimationFrame(follow);
  }

  function play() {
    window.LiveEnglish.stop();
    if (video.currentTime >= sceneEnd || video.currentTime < sceneStart) video.currentTime = sceneStart;
    video.play().catch(function (error) {
      if (error.name !== 'AbortError') window.console.error(error);
    });
  }

  function togglePlay() {
    if (video.paused) play();
    else video.pause();
  }

  function setRepeatLine(line) {
    if (repeatLine) repeatLine.querySelector('.line-repeat').setAttribute('aria-pressed', 'false');
    repeatLine = line;
    if (line) line.querySelector('.line-repeat').setAttribute('aria-pressed', 'true');
  }

  video.addEventListener('play', function () {
    playButton.classList.add('playing');
    requestAnimationFrame(follow);
  });
  video.addEventListener('pause', function () { playButton.classList.remove('playing'); });
  video.addEventListener('timeupdate', function () {
    if (!video.paused) holdInRange();
    show();
  });
  video.addEventListener('click', togglePlay);
  playButton.addEventListener('click', togglePlay);

  bar.querySelector('.p-stop').addEventListener('click', function () {
    video.pause();
    setRepeatLine(null);
    moveTo(sceneStart);
    highlight(null);
  });
  bar.querySelector('.p-back').addEventListener('click', function () { moveTo(video.currentTime - SKIP_SECONDS); });
  bar.querySelector('.p-forward').addEventListener('click', function () { moveTo(video.currentTime + SKIP_SECONDS); });

  loopButton.addEventListener('click', function () {
    loopScene = !loopScene;
    loopButton.setAttribute('aria-pressed', loopScene ? 'true' : 'false');
  });

  seek.addEventListener('input', function () {
    dragging = true;
    timeLabel.textContent = clockText(parseFloat(seek.value));
  });
  seek.addEventListener('change', function () {
    dragging = false;
    setRepeatLine(null);
    moveTo(sceneStart + parseFloat(seek.value));
  });

  speedButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      var speed = parseFloat(button.dataset.speed);
      video.defaultPlaybackRate = speed;
      video.playbackRate = speed;
      speedButtons.forEach(function (other) {
        other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
      });
    });
  });

  script.addEventListener('click', function (event) {
    var repeat = event.target.closest('.line-repeat');
    if (repeat) {
      var line = repeat.closest('.bubble');
      if (line === repeatLine) {
        setRepeatLine(null);
      } else {
        setRepeatLine(line);
        moveTo(parseFloat(line.dataset.start));
        play();
      }
      return;
    }
    var word = event.target.closest('.pw');
    if (word) {
      setRepeatLine(null);
      moveTo(parseFloat(word.dataset.t));
      play();
    }
  });

  grid.querySelector('.hide-script').addEventListener('change', function (event) {
    script.classList.toggle('script-hidden', event.target.checked);
  });

  document.addEventListener('tabchange', function () { video.pause(); });

  show();
})();
