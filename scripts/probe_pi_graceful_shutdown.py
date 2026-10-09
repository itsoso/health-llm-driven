"""Probe owned local uvicorn/Pi shutdown; no provider calls or database access."""
import concurrent.futures, json, os, pathlib, signal, socket, subprocess, sys, tempfile, time, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
CHILD='''import asyncio, json, os, pathlib, sys
sys.path.insert(0, str(ROOT / "backend"))
from app.services.pi_kernel import PiKernelSession
import uvicorn
async def app(scope, receive, send):
    if scope['type'] != 'http': return
    try:
        async with PiKernelSession() as session:
            await session.start(messages=[{'role':'user','content':'public weather probe'}],tools=[],max_turns=2)
            request=await anext(session)
            marker.write_text(str(session.process.pid))
            await asyncio.sleep(1.2)
            await session.respond(request,content='synthetic weather answer',tool_calls=[],finish_reason='stop')
            frame=await anext(session)
            result={'status':'complete','content':frame['content'],'child_reaped':session.returncode is not None}
    except Exception as exc:
        result={'status':'error','error_type':type(exc).__name__}
    body=json.dumps(result).encode()
    await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
    await send({'type':'http.response.body','body':body})
uvicorn.run(app,fd=fd,loop='uvloop',lifespan='off',timeout_graceful_shutdown=30,log_level='error',access_log=False)
'''
results=[]
for mode in ['control_group','main_only']:
 for attempt in range(3):
  with tempfile.TemporaryDirectory(prefix='reva-graceful-') as directory:
   marker=pathlib.Path(directory)/'ready'
   with socket.socket() as listener:
    listener.bind(('127.0.0.1',0));listener.listen(8)
    fd=listener.fileno();port=listener.getsockname()[1]
    source='import pathlib\nROOT=pathlib.Path('+repr(str(ROOT))+')\nmarker=pathlib.Path('+repr(str(marker))+')\nfd='+str(fd)+'\n'+CHILD
    proc=subprocess.Popen([sys.executable,'-B','-c',source],pass_fds=[fd],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def request():
     with urllib.request.urlopen('http://127.0.0.1:'+str(port),timeout=10) as response:return json.load(response)
    try:
     with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
      response=pool.submit(request)
      deadline=time.monotonic()+8
      while not marker.exists():
       if time.monotonic()>deadline:raise RuntimeError('probe_start_timeout')
       time.sleep(.02)
      child=int(marker.read_text())
      if mode=='control_group':os.killpg(proc.pid,signal.SIGTERM)
      else:proc.send_signal(signal.SIGTERM)
      result=response.result(timeout=10)
      proc.wait(timeout=8)
      try:os.kill(child,0);reaped=False
      except ProcessLookupError:reaped=True
      results.append({'mode':mode,'attempt':attempt+1,**result,'child_gone':reaped,'server_exit':proc.returncode})
    finally:
     if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
assert all(r['status']=='error' for r in results if r['mode']=='control_group'),results
assert all(r['status']=='complete' and r['child_reaped'] and r['child_gone'] for r in results if r['mode']=='main_only'),results
print(json.dumps({'scope':'Local uvicorn uvloop and real Pi; synthetic answer; owned process signals emulate initial systemd kill scope; not live systemd or provider proof','results':results},indent=2))
