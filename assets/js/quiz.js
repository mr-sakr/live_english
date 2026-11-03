// Picture quiz: plays a word from the page, the learner clicks its picture.
// Questions are read from the page's own word cards, so there is no extra data to load.
(function () {
  var OPTION_COUNT = 6;
  var NEXT_AFTER_RIGHT = 1700;
  var NEXT_AFTER_WRONG = 3200;

  var root = document.querySelector('.quiz');
  var cards = document.querySelectorAll('[data-panel="words"] .card');
  if (!root || !cards.length) return;

  var items = Array.prototype.map.call(cards, function (card) {
    var ipa = card.querySelector('.ipa');
    return {
      text: card.querySelector('h2').textContent,
      ipa: ipa ? ipa.textContent : '',
      meaning: card.querySelector('.meaning').textContent,
      image: card.querySelector('img').getAttribute('src'),
      sound: card.querySelector('.spk.big').dataset.src
    };
  });

  var round = [];
  var index = 0;
  var score = 0;
  var wrong = [];
  var timer = null;
  var waitingForNext = false;

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

  // Wrong choices never repeat a picture, and never share the right answer's picture.
  function optionsFor(item) {
    var used = {};
    used[item.image] = true;
    var options = [item];
    shuffled(items).forEach(function (other) {
      if (options.length < OPTION_COUNT && !used[other.image]) {
        used[other.image] = true;
        options.push(other);
      }
    });
    return shuffled(options);
  }

  function start(list) {
    round = shuffled(list);
    index = 0;
    score = 0;
    wrong = [];
    showQuestion();
  }

  function showQuestion() {
    var item = round[index];
    root.innerHTML =
      '<div class="quiz-bar"><span>السؤال ' + (index + 1) + ' من ' + round.length + '</span>' +
      '<strong class="quiz-score">النتيجة: ' + score + '</strong></div>' +
      '<div class="bar"><span style="width:' + (index * 100 / round.length) + '%"></span></div>' +
      '<div class="quiz-prompt"><button type="button" class="spk big quiz-word" aria-label="أعد سماع الكلمة" title="أعد سماع الكلمة"></button>' +
      '<div class="quiz-result" role="status">أين صورة هذه الكلمة؟</div></div>' +
      '<div class="quiz-options"></div>';

    var speaker = root.querySelector('.quiz-word');
    speaker.dataset.src = item.sound;

    var grid = root.querySelector('.quiz-options');
    optionsFor(item).forEach(function (option, position) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'quiz-option';
      button.setAttribute('aria-label', 'الصورة ' + (position + 1));
      var image = document.createElement('img');
      image.src = option.image;
      image.alt = '';
      button.appendChild(image);
      button.addEventListener('click', function () { answer(option, button, item); });
      if (option === item) button.dataset.right = 'true';
      grid.appendChild(button);
    });

    window.LiveEnglish.play(speaker);
  }

  function answer(option, button, item) {
    var isRight = option === item;
    root.querySelectorAll('.quiz-option').forEach(function (other) {
      other.disabled = true;
      if (other.dataset.right) other.classList.add('right');
    });
    if (isRight) {
      score++;
    } else {
      button.classList.add('wrong');
      wrong.push(item);
      window.LiveEnglish.play(root.querySelector('.quiz-word'));
    }
    root.querySelector('.quiz-score').textContent = 'النتيجة: ' + score;

    var result = root.querySelector('.quiz-result');
    result.className = 'quiz-result ' + (isRight ? 'is-right' : 'is-wrong');
    result.innerHTML = '<strong></strong> <span lang="en" dir="ltr" class="quiz-answer"></span> ' +
      '<span lang="en" dir="ltr" class="ipa"></span> <span class="quiz-meaning"></span>';
    result.querySelector('strong').textContent = isRight ? '✓ صح:' : '✗ غلط، الإجابة الصحيحة:';
    result.querySelector('.quiz-answer').textContent = item.text;
    result.querySelector('.ipa').textContent = item.ipa;
    result.querySelector('.quiz-meaning').textContent = item.meaning;

    waitingForNext = true;
    timer = setTimeout(next, isRight ? NEXT_AFTER_RIGHT : NEXT_AFTER_WRONG);
  }

  function next() {
    waitingForNext = false;
    index++;
    if (index < round.length) showQuestion();
    else showResult();
  }

  function showResult() {
    var total = round.length;
    var percent = Math.round(score * 100 / total);
    root.innerHTML =
      '<div class="quiz-final"><strong>' + score + ' من ' + total + '</strong><span>' + percent + '%</span></div>' +
      '<div class="quiz-missed"></div>' +
      '<div class="quiz-actions"><button type="button" class="quiz-go">أعد الاختبار</button></div>';

    if (wrong.length) {
      var missed = root.querySelector('.quiz-missed');
      var title = document.createElement('h2');
      title.textContent = 'كلمات تحتاج إلى مراجعة';
      missed.appendChild(title);
      var list = document.createElement('ul');
      wrong.forEach(function (item) {
        var row = document.createElement('li');
        var word = document.createElement('span');
        word.lang = 'en';
        word.dir = 'ltr';
        word.textContent = item.text;
        row.appendChild(word);
        row.appendChild(document.createTextNode(' — ' + item.meaning));
        list.appendChild(row);
      });
      missed.appendChild(list);

      var retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'quiz-retry';
      retry.textContent = 'أعد الأخطاء فقط';
      var again = wrong.slice();
      retry.addEventListener('click', function () { start(again); });
      root.querySelector('.quiz-actions').appendChild(retry);
    }
  }

  root.addEventListener('click', function (event) {
    if (event.target.closest('.quiz-go')) start(items);
  });

  // Leaving the tab pauses the round; coming back resumes it.
  document.addEventListener('tabchange', function (event) {
    clearTimeout(timer);
    if (event.detail !== 'quiz') return;
    if (waitingForNext) {
      next();
    } else if (root.querySelector('.quiz-word')) {
      window.LiveEnglish.play(root.querySelector('.quiz-word'));
    }
  });
})();
