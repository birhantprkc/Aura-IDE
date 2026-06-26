import json, sys, time
payload = json.loads(sys.stdin.read())
time.sleep(30)
print(json.dumps({'ok': True, 'finished': True}))
