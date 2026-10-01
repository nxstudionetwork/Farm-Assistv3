import re
s = open(r'C:\Users\AICOE 5\Downloads\Farm_Assist.Application\frontend\tools.html', encoding='utf-8').read()
stack = []
voids = set('area base br col embed hr img input link meta param source track wbr'.split())
for m in re.finditer(r'<(/?)([a-zA-Z0-9-]+)((?:"[^"]*"|[^>])*?)(/?)>', s):
    if m.group(1):
        if stack and stack[-1] == m.group(2).lower():
            stack.pop()
    else:
        tag = m.group(2).lower()
        if not (m.group(4) == '/' or tag in voids):
            stack.append(tag)
print('unclosed', stack[:20])