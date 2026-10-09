"""Receive initial credentials on stdin only; output identifiers, never credentials."""
import json
import sys
from dataclasses import asdict
from app.services.install_bootstrap import create_first_teacher, BootstrapError

def run(sqlite_url, stdin, stdout):
    text=stdin.read(16385)
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise ValueError('duplicate')
            out[k]=v
        return out
    try:
        if len(text.encode('utf-8'))>16384: raise ValueError('limit')
        data=json.loads(text,object_pairs_hook=pairs)
        if not isinstance(data,dict) or set(data)!={'username','password'} or not all(isinstance(x,str) for x in data.values()): raise ValueError('shape')
    except (ValueError,TypeError):
        raise BootstrapError('invalid bootstrap input') from None
    result=create_first_teacher(sqlite_url,data['username'],data['password'])
    stdout.write(json.dumps(asdict(result))+'\n')

def main():
    try:
        from app.config import load_settings
        from app.services.startup import validate_schema_current
        settings=load_settings()
        validate_schema_current(settings)
        run(settings.SQLITE_URL,sys.stdin,sys.stdout)
    except Exception:
        print('Initial teacher bootstrap failed; existing accounts were preserved.',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
