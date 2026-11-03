// Film scene player: plays one stretch of the film, highlights the script and repeats single lines.
// Silent stretches are jumped over rather than cut, so the film's own clock keeps the script in sync.
// The bar counts only the time that will really play.
(function () {
  var SKIP_SECONDS = 5;
  var LONGEST_PAUSE = 3;
  var LINE_PADDING = 0.6;

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
  var skipSilence = grid.querySelector('.skip-silence');
  var totalLabel = bar.querySelector('.p-total');
  var segments = [];
  var activeWord = null;
  var repeatLine = null;
  var loopScene = false;
  var dragging = false;

  function clockText(value) {
    var whole = Math.floor(Math.max(value, 0));
    var rest = whole % 60;
    return Math.floor(whole / 60) + ':' + (rest < 10 ? '0' : '') + rest;
  }

  // The stretches that will play: lines closer than LONGEST_PAUSE stay together.
  function buildSegments() {
    segments = [];
    if (!skipSilence.checked) {
      segments.push({ start: sceneStart, end: sceneEnd });
    } else {
      script.querySelectorAll('.bubble').forEach(function (line) {
        var start = parseFloat(line.dataset.start);
        var end = parseFloat(line.dataset.end);
        var last = segments[segments.length - 1];
        if (last && start - last.lastLine <= LONGEST_PAUSE) {
          last.end = Math.min(end + LINE_PADDING, sceneEnd);
          last.lastLine = end;
        } else {
          segments.push({ start: Math.max(start - LINE_PADDING, sceneStart), end: Math.min(end + LINE_PADDING, sceneEnd), lastLine: end });
        }
      });
    }
    var total = playedTime(sceneEnd);
    seek.max = total;
    totalLabel.textContent = clockText(total);
  }

  function firstMoment() {
    return segments[0].start;
  }

  function lastMoment() {
    return segments[segments.length - 1].end;
  }

  // Film time -> time on the bar, leaving out what gets skipped.
  function playedTime(time) {
    var played = 0;
    for (var i = 0; i < segments.length; i++) {
      if (time >= segments[i].end) played += segments[i].end - segments[i].start;
      else if (time > segments[i].start) played += time - segments[i].start;
    }
    return played;
  }

  // Time on the bar -> film time.
  function filmTime(played) {
    for (var i = 0; i < segments.length; i++) {
      var length = segments[i].end - segments[i].start;
      if (played <= length) return segments[i].start + Math.max(played, 0);
      played -= length;
    }
    return lastMoment();
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
    video.currentTime = Math.max(firstMoment(), Math.min(time, lastMoment()));
    show();
  }

  // Keeps playback inside the repeated line or the scene, and jumps over silent stretches.
  function holdInRange() {
    if (video.seeking) return;
    var time = video.currentTime;
    if (repeatLine) {
      var lineStart = parseFloat(repeatLine.dataset.start);
      var lineEnd = parseFloat(repeatLine.dataset.end);
      if (time >= lineEnd || time < lineStart - 0.5) video.currentTime = lineStart;
    } else if (time >= lastMoment()) {
      if (loopScene) {
        video.currentTime = firstMoment();
      } else {
        video.pause();
        video.currentTime = lastMoment();
      }
    } else {
      for (var i = 0; i < segments.length; i++) {
        // A finished jump can land a hair before its target, and must not trigger another.
        if (time < segments[i].start - 0.05) {
          video.currentTime = segments[i].start;
          return;
        }
        if (time < segments[i].end) return;
      }
    }
  }

  function show() {
    var time = video.currentTime;
    var index = wordIndexAt(time);
    highlight(index >= 0 && time < lastMoment() ? words[index] : null);
    var played = playedTime(time);
    if (!dragging) seek.value = played;
    timeLabel.textContent = clockText(played);
  }

  function follow() {
    if (video.paused) return;
    holdInRange();
    show();
    requestAnimationFrame(follow);
  }

  function play() {
    window.LiveEnglish.stop();
    if (video.currentTime >= lastMoment() || video.currentTime < firstMoment() - 0.05) video.currentTime = firstMoment();
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
    moveTo(firstMoment());
    highlight(null);
  });
  bar.querySelector('.p-back').addEventListener('click', function () {
    moveTo(filmTime(playedTime(video.currentTime) - SKIP_SECONDS));
  });
  bar.querySelector('.p-forward').addEventListener('click', function () {
    moveTo(filmTime(playedTime(video.currentTime) + SKIP_SECONDS));
  });

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
    moveTo(filmTime(parseFloat(seek.value)));
  });

  skipSilence.addEventListener('change', function () {
    buildSegments();
    show();
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

  buildSegments();
  show();
})();
