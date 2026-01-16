import importlib, sys
mods = ['utils','solver','data_loader','reports','auth']
ok = True
for m in mods:
    try:
        importlib.import_module(m)
        print('OK', m)
    except Exception as e:
        print('ERR', m, repr(e))
        ok = False
sys.exit(0 if ok else 1)
