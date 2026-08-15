# TPipe Tuner Default Stress-Test String

The built-in default string used when `--test-string` is not supplied. Covers: common prose, rare vocabulary, OOV/nonsense words, numbers/formats, IPs/dates/phones, symbols/currency, programming casing styles, JSON/HTML/code syntax, URLs/emails, multilingual Unicode, emoji/ZWJ sequences, and whitespace anomalies.

```
The quick brown fox jumps over the lazy dog.
Now, let's test some less common vocabulary: defenestration, floccinaucinihilipilification, antidisestablishmentarianism, and pneumonoultramicroscopicsilicovolcanoconiosis.
How about nonsense or out-of-vocabulary (OOV) words? Twas brillig, and the slithy toves did gyre. Asdfghjkl qwertyuiop zxcvbnm123! xqxqxqxq ptakh.
Let's stress test numbers and formats: 42, 0, -273.15, 6.022e23, NaN, Infinity.
IP Address: 192.168.255.255, IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334.
Dates and Times: 2026-03-14T09:32:42Z, 14/03/2026, March 14th, 2026.
Phone: +1-(800)-555-0199 ext. 1234.
Symbols, Punctuation, and Currency:
!@#$%^&*()_+-=[]{}|;':",./<>?`~\\
$1,000.00, €50.99, ¥10000, £20, ₹500.
Programming syntaxes and casings:
camelCaseVariable, PascalCaseClass, snake_case_function, kebab-case-id, sPoNgEbObCaSe, SCREAMING_SNAKE_CASE.
{"json_key": ["value1", "value2\n", null, true]}
<html lang="en"><head><title>Test</title></head><body>hello</body></html>
def foo(x: int) -> int: return x ** 2
URLs and Emails:
john.doe+spamfilter@subdomain.co.uk
https://www.example-site.com:8080/path/to/resource.html?query=token&sort=desc#fragment-identifier
Unicode, Accents, and Multilingual Support:
café, naïve, jalapeño, façade, über.
Russian: Привет, мир!
Chinese: 你好，世界！
Japanese: こんにちは世界
Arabic: مرحبا بالعالم
Korean: 안녕하세요
Emojis and Zero-Width Joiners (ZWJ):
😀🚀🤖✨
Family (ZWJ sequence): 👨‍👩‍👧‍👦
Facepalm with skin tone (Modifiers): 🤦🏽‍♀️
Kaomoji: ¯\_(ツ)_/¯ (╯°□°）╯︵ ┻━┻
Whitespace anomalies (spaces, tabs, newlines):
\tLeading tab.    Four spaces.
Multiple\n\n\nnewlines and \r\n carriage returns.
Trailing spaces ->
As a default test string, that if a test string is not supplied. This is what gets passed through. Since this is a pretty solid and universal stress tester for most tokenizers this string should be generally optimized to get the tuning correct most of the time.
```

To emit this string: `./TPipe-Tuner/tuner.sh --print-default-string`
