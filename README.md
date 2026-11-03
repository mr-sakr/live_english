# Live English

افتح `index.html` مباشرة من المجلد. البرنامج يعمل بالكامل بدون إنترنت.

## التنظيم

```
index.html                 الصفحة الرئيسية
assets/                    التنسيق والجافاسكربت المشتركان
topics/<topic>/            صفحات الموضوع (مولَّدة، لا تُعدَّل يدويًا)
    <group>/<section>/     صفحة خفيفة لكل قسم
    media/images/          صور الموضوع
    media/audio/           أصوات الموضوع (us, uk, sentences, conversations, paragraphs)
content/<topic>/           المحتوى الأصلي: عدّل هنا
tools/                     أداة البناء
```

## صيغ ملفات المحتوى

كل سطر عنصر، والأعمدة مفصولة بـ `|`.

- كلمات: `word|ipa|pos|arabic|image|example|example_arabic`
- تعبيرات: `phrase|arabic|image|example|example_arabic`
- جمل: `## عنوان المجموعة` ثم `english|arabic`
- محادثات: `## English title | العنوان` ثم `A|english|arabic`
- قصة الصفحة `<section>.story.txt` لكل صفحة كلمات أو تعبيرات: `## conversation` ثم `A|english|arabic`، و`## paragraph` ثم `english|arabic`

يجب أن تحتوي المحادثة والفقرة كل كلمات الصفحة بصيغتها نفسها، وإلا يتوقف البناء ويذكر الكلمات الناقصة.

الصورة إما رمز تعبيري (`⌚`) وإما رسم: `clock:3:15`, `digital:07:45`, `month:1`, `day:1`, `day:6-7`,
`sky:noon`, `tile:60 min`, `face`, `sundial`, `timetable`, `days:-1`, `freq:8:🚶`.

أو مشهد مركب، ويمكن وضع أي رسم بين قوسين داخله مثل `[clock:3:15]`:
`pair:A>B` (ترتيب)، `together:A+B` (معًا)، `badge:A/B` (تفصيلة على الزاوية)، `no:A` (ممنوع)، `rep:A*3` (تكرار)،
`grid:A,B,C,D`، `cap:A~text` (تعليق قصير)، `tl:30~A~text` (خط زمني بنقطة، أو `20-50` مدة، أو `10,35,65` عدة نقاط).

لا يجوز تكرار صورة لعنصرين في الموضوع نفسه، وإلا يتوقف البناء ويذكر التكرار.

## البناء

```bash
pip install -r tools/requirements.txt
python tools/build.py
```

البناء يحمّل الصور والأصوات الناقصة فقط، ويحتاج إلى إنترنت لذلك. `--pages` يعيد إنشاء الصفحات فقط.

## الدروس الصوتية للموبايل

```bash
python tools/audio_lessons.py
```

تُنشئ مجلد `mobile-audio/` بعد تشغيل البناء. انقله إلى الموبايل واستخدم أي مشغل صوت.
لكل قسم `1-recall` (افتكر الكلمة) و`2-repeat` (ردّد الجملة) و`3-conversation` (المحادثة)، ولكل موضوع `all-paragraphs`.
لبناء قسم واحد فقط: `python tools/audio_lessons.py clocks`
