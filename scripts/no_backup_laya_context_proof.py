"""Read-only Laya evidence for a failed context before prepare/activate.

No service mutation, credential copy, inference, restoration or retry exists here.
Historical consumers inspect saved identities and canonical source only.
"""
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

ASSETS = ('install.py', 'serve.py', 'model-manifest.json', 'requirements.lock',
          'reva-laya.service.in', 'encoder-config.json.b64', 'rl-agent-config.json.b64',
          'tokenizer-config.json.b64', 'model-NOTICE.txt')
STATE = Path('/var/lib/reva-laya-release')
BASE = Path('/opt/reva-laya')
UNIT = Path('/etc/systemd/system/reva-laya.service')
ENV = Path('/etc/reva-laya/service.env')
HEALTH = {'status': 'ok', 'loaded': ['multilingual'], 'device': 'cpu'}


class LayaContextError(RuntimeError):
    pass


def _object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise LayaContextError('duplicate Laya evidence key')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise LayaContextError('Laya evidence must be an object')
    return value


def _stamp(path):
    info = path.lstat()
    return [info.st_ctime_ns, info.st_mtime_ns]


def _old_file(proof, path, mode, lease_ns):
    before = _stamp(path)
    raw, identity = proof._file(path, mode)
    if _stamp(path) != before or max(before) >= lease_ns:
        raise LayaContextError('Laya file did not predate lease or changed')
    return raw, identity, before


def _model(proof, path, metadata, lease_ns):
    proof._secure_evidence(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != 0
            or before.st_gid != 0 or stat.S_IMODE(before.st_mode) != 0o644
            or before.st_size != metadata['bytes'] or not 0 < before.st_size <= 1_000_000_000
            or max(before.st_ctime_ns, before.st_mtime_ns) >= lease_ns):
        raise LayaContextError('installed model metadata differs')
    def stamp(info):
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
                info.st_nlink, info.st_size, info.st_ctime_ns, info.st_mtime_ns)
    cache = getattr(proof, '_laya_model_memo', {})
    key = (str(path), stamp(before))
    digest = cache.get(key)
    if digest is None:
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if stamp(path.lstat()) != stamp(before) or digest != metadata['sha256']:
        raise LayaContextError('installed model contents differ')
    cache[key] = digest
    proof._laya_model_memo = cache
    return {'dev': before.st_dev, 'ino': before.st_ino, 'uid': before.st_uid,
            'gid': before.st_gid, 'mode': 0o644, 'sha256': digest}, _stamp(path)


class NoHealthRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise LayaContextError('health redirect forbidden')


def health_get():
    opener = build_opener(ProxyHandler({}), NoHealthRedirect())
    with opener.open('http://127.0.0.1:8092/health', timeout=5) as response:
        raw = response.read(4097)
        if response.status != 200 or len(raw) > 4096 or _object(raw) != HEALTH:
            raise LayaContextError('Laya health GET contract differs')
    return dict(HEALTH)


def _process(proof, installer, generation, config, boot, lease_ns):
    unit = 'reva-laya.service'
    fields = installer.service_identity(generation)
    for key in ('NeedDaemonReload', 'ActiveEnterTimestampMonotonic', 'ControlGroup',
                'WorkingDirectory', 'EnvironmentFiles', 'ExecStart'):
        fields[key] = proof.systemd.show(unit, key)
    expected_exec = (f'path={generation}/venv/bin/python\nargv[]={generation}/venv/bin/python '
                     f'-I {generation}/serve.py\nignore_errors=no')
    effective = proof.runtime.ReleaseTransaction._stable_exec_start(None, fields['ExecStart'])
    if (fields['NeedDaemonReload'] != 'no' or fields['WorkingDirectory'] != str(generation)
            or fields['EnvironmentFiles'] != str(installer.ENV) + ' (ignore_errors=no)'
            or effective != expected_exec or fields['NRestarts'] != '0'):
        raise LayaContextError('effective Laya service differs')
    fields['ExecStart'] = effective
    pid = fields['MainPID']
    if proof._pids(unit) != [pid]:
        raise LayaContextError('Laya process inventory differs')
    process = proof.proc / pid
    before = (process / 'stat').read_bytes().rsplit(b')', 1)[-1].split()
    with (process / 'environ').open('rb') as handle:
        raw = handle.read(1_000_001)
    if (len(raw) > 1_000_000 or [v for v in raw.split(b'\0') if v.startswith(b'LAYA_API_KEY=')]
            != [('LAYA_API_KEY=' + config['DECISION_API_KEY']).encode()]):
        raise LayaContextError('Laya process credential authority differs')
    after = (process / 'stat').read_bytes().rsplit(b')', 1)[-1].split()
    if len(before) < 20 or len(after) < 20 or before[19] != after[19] or not before[19].isdigit():
        raise LayaContextError('Laya process identity changed')
    ticks = os.sysconf('SC_CLK_TCK')
    if (boot + int(before[19]) / ticks >= lease_ns / 1_000_000_000 - 60
            or boot + int(fields['ActiveEnterTimestampMonotonic']) / 1_000_000 >= lease_ns / 1_000_000_000 - 60):
        raise LayaContextError('Laya generation does not predate lease')
    fields['processes'] = {pid: before[19].decode()}
    fields['boot_id'] = (proof.proc / 'sys/kernel/random/boot_id').read_text().strip()
    listener = installer.command(['/usr/bin/ss', '-H', '-lntp', 'sport = :8092'])
    lines = listener.splitlines()
    if (len(lines) != 1 or len(lines[0].split()) < 6
            or lines[0].split()[3] != '127.0.0.1:8092'
            or re.findall(r'pid=([0-9]+)', listener) != [pid]):
        raise LayaContextError('Laya health listener is not the proven process')
    return fields


def inspect(proof, failed_source, old_source, live_identity):
    """Read only canonical/live files and current service metadata; never infer."""
    lease_ns = proof._chronology['lease_started_ns']
    env_path = proof.production / 'backend/.env'
    raw, env_identity = proof._file(env_path, 0o640)
    env_stamp = _stamp(env_path)
    if (env_identity != live_identity or env_stamp != [proof._chronology['env_ctime_ns'],
                                                     proof._chronology['env_mtime_ns']]):
        raise LayaContextError('current configuration changed before Laya proof')
    assets = {}
    for name in ASSETS:
        canonical = proof._file(old_source / 'infra/laya' / name)[0]
        if any(proof._file(root / 'infra/laya' / name)[0] != canonical
               for root in (failed_source, proof.source)):
            raise LayaContextError('canonical Laya assets changed')
        assets[name] = hashlib.sha256(canonical).hexdigest()
    # old_has_decisions is the exact producer's git path predicate.
    old_decisions = old_source / 'backend/app/config.py'
    witness, witness_id = proof._file(old_decisions)
    if not re.search(rb'decision_provider|DECISION_PROVIDER|decide_route|/v1/systemone|127[.]0[.]0[.]1:8092', witness):
        raise LayaContextError('old backend decision predicate is not proven')
    exported = STATE / 'sources' / proof.failed_sha
    export = {'directory': proof._directory(exported), 'files': {}}
    if {p.name for p in exported.iterdir()} != set(ASSETS) | {'source.json'}:
        raise LayaContextError('Laya exported source inventory differs')
    for name in (*ASSETS, 'source.json'):
        content, export['files'][name] = proof._file(exported / name, 0o400)
        if name == 'source.json':
            export['manifest'] = _object(content)
        elif hashlib.sha256(content).hexdigest() != assets[name]:
            raise LayaContextError('Laya exported asset differs')
    if (type(export['manifest'].get('old_has_decisions')) is not bool
            or export['manifest'] != {'sha': proof.failed_sha, 'old_sha': proof.production_sha,
                               'old_has_decisions': True, 'files': assets}):
        raise LayaContextError('Laya source manifest binding differs')
    installer = proof._module('infra/laya/install.py', 'no_backup_laya_live_config')
    config = installer.parse_config(raw.decode())
    if config is None:
        raise LayaContextError('current configuration does not select Laya')
    generation, expected_unit, expected_env, expected = installer.expected_install(old_source / 'infra/laya', config)
    if installer.expected_install(failed_source / 'infra/laya', config)[3] != expected:
        raise LayaContextError('failed Laya generation differs')
    receipt_raw, receipt_id, receipt_time = _old_file(proof, STATE / 'install.json', 0o600, lease_ns)
    receipt = _object(receipt_raw)
    if (set(receipt) != {'generation','unit_sha256','env_sha256','state','candidate_sha','lease'}
            or receipt.get('state') != 'INSTALLED'
            or re.fullmatch(r'[0-9a-f]{40}', receipt.get('candidate_sha', '')) is None
            or receipt['candidate_sha'] == proof.failed_sha
            or re.fullmatch(r'[0-9a-f]{64}', receipt.get('lease', '')) is None
            or any(receipt.get(k) != v for k,v in expected.items())):
        raise LayaContextError('existing Laya receipt differs')
    origin = proof.bootstrap.canonical_source(receipt['candidate_sha'])
    if installer.expected_install(origin / 'infra/laya', config)[3] != expected:
        raise LayaContextError('original Laya generation differs')
    success_path = proof.bootstrap.STATE / proof.production_sha / 'completed.json'
    success, success_id, success_time = _old_file(proof, success_path, 0o600, lease_ns)
    if (_object(success) != {'sha': proof.production_sha, 'state': 'SUCCEEDED'}
            or max(receipt_time) >= min(success_time)):
        raise LayaContextError('installed Laya receipt does not predate old success')
    proof._absent(STATE / 'install.json.pending', installer.UNIT.with_name(installer.UNIT.name + '.pending'),
                  installer.ENV.with_name(installer.ENV.name + '.pending'))
    unit, unit_id, unit_time = _old_file(proof, installer.UNIT, 0o644, lease_ns)
    env, service_env_id, service_env_time = _old_file(proof, installer.ENV, 0o640, lease_ns)
    if unit != expected_unit or env != expected_env or service_env_id['gid'] != installer.validate_account().pw_gid:
        raise LayaContextError('existing Laya unit or config differs')
    files = {'unit': unit_id, 'env': service_env_id, 'generation': proof._directory(generation, 0o755),
             'assets': {}, 'models': {}}
    chronology = {'receipt': receipt_time, 'production_success': success_time, 'unit': unit_time,
                  'env': service_env_time, 'generation': _stamp(generation), 'assets': {}, 'models': {}}
    if max(chronology['generation']) >= lease_ns:
        raise LayaContextError('generation directory did not predate lease')
    for name in ASSETS:
        content, files['assets'][name], chronology['assets'][name] = _old_file(proof, generation / name, 0o644, lease_ns)
        if hashlib.sha256(content).hexdigest() != assets[name]:
            raise LayaContextError('installed generation asset differs')
    manifest = _object(proof._file(old_source / 'infra/laya/model-manifest.json')[0])
    for name, metadata in manifest['files'].items():
        if re.fullmatch(r'[A-Za-z0-9_./-]+', name) is None or '..' in Path(name).parts or name.startswith('/'):
            raise LayaContextError('model manifest path invalid')
        files['models'][name], chronology['models'][name] = _model(proof, generation / 'models' / name, metadata, lease_ns)
    boots = re.findall(r'^btime ([0-9]+)$', (proof.proc / 'stat').read_text(), re.M)
    if len(boots) != 1:
        raise LayaContextError('Laya boot time unavailable')
    boot = int(boots[0])
    before = _process(proof, installer, generation, config, boot, lease_ns)
    health = health_get()
    if _process(proof, installer, generation, config, boot, lease_ns) != before:
        raise LayaContextError('Laya process changed during GET')
    if proof._file(env_path, 0o640)[1] != live_identity or _stamp(env_path) != env_stamp:
        raise LayaContextError('current configuration changed during Laya proof')
    for path, expected_id, stamps in ((STATE / 'install.json', receipt_id, receipt_time),
                                     (installer.UNIT, unit_id, unit_time),
                                     (installer.ENV, service_env_id, service_env_time)):
        if proof._file(path)[1] != expected_id or _stamp(path) != stamps:
            raise LayaContextError('existing Laya identity changed during proof')
    if _stamp(generation) != chronology['generation']:
        raise LayaContextError('generation directory changed during proof')
    for name in ASSETS:
        if _stamp(generation / name) != chronology['assets'][name]:
            raise LayaContextError('generation asset metadata changed during proof')
    for name in manifest['files']:
        if _stamp(generation / 'models' / name) != chronology['models'][name]:
            raise LayaContextError('model metadata changed during proof')
    result = {'profile': 'live-config-installed-v1', 'failed_sha': proof.failed_sha,
              'production_sha': proof.production_sha, 'started_at': proof._started_text,
              'live_env': live_identity, 'assets': assets, 'source_export': export,
              'old_decision_witness': witness_id,
              'origin_sha': receipt['candidate_sha'], 'expected': expected, 'receipt': receipt_id,
              'production_success': success_id, 'files': files, 'chronology': chronology,
              'services': before, 'health': health, 'boot_seconds': boot,
              'ticks_per_second': os.sysconf('SC_CLK_TCK'), 'model_manifest': manifest}
    validate(result, proof.failed_sha, proof.production_sha, lease_ns, live_identity)
    # A read-only GET may overlap another operator's preparation intent. Keep
    # both ordinary and dangling pending paths absent through the final proof.
    proof._absent(STATE / 'install.json.pending', installer.UNIT.with_name(installer.UNIT.name + '.pending'),
                  installer.ENV.with_name(installer.ENV.name + '.pending'))
    return result


def _identity(value, mode, directory=False, gid=0):
    keys = {'dev','ino','uid','gid','mode'} | (set() if directory else {'sha256'})
    if (not isinstance(value, dict) or set(value) != keys
            or any(type(value[k]) is not int or value[k] < 0 for k in keys - {'sha256'})
            or value['ino'] <= 0 or value['uid'] != 0 or value['mode'] != mode or value['mode'] & 0o022
            or (gid is not None and value['gid'] != gid)
            or (not directory and re.fullmatch(r'[0-9a-f]{64}', value['sha256']) is None)):
        raise LayaContextError('saved Laya identity differs')


def validate(value, failed_sha, production_sha, lease_ns, live_identity):
    """Strict historical grammar. No live filesystem, process or network reads."""
    keys = {'profile','failed_sha','production_sha','started_at','live_env','assets','source_export',
            'origin_sha','expected','receipt','production_success','files','chronology','services',
            'health','boot_seconds','ticks_per_second','model_manifest','old_decision_witness'}
    if (not isinstance(value, dict) or set(value) != keys or value['profile'] != 'live-config-installed-v1'
            or value['failed_sha'] != failed_sha or value['production_sha'] != production_sha
            or value['live_env'] != live_identity or value['health'] != HEALTH
            or re.fullmatch(r'[0-9a-f]{40}', value['origin_sha']) is None or value['origin_sha'] == failed_sha
            or type(value['boot_seconds']) is not int or value['boot_seconds'] <= 0
            or type(value['ticks_per_second']) is not int or not 1 <= value['ticks_per_second'] <= 10000
            or int(datetime.strptime(value['started_at'], '%Y-%m-%dT%H:%M:%SZ\n').replace(tzinfo=UTC).timestamp()*1_000_000_000) != lease_ns):
        raise LayaContextError('saved Laya profile differs')
    _identity(value['live_env'], 0o640, gid=None)
    _identity(value['old_decision_witness'], value['old_decision_witness'].get('mode'))
    assets = value['assets']
    if not isinstance(assets, dict) or set(assets) != set(ASSETS) or any(re.fullmatch(r'[0-9a-f]{64}', v) is None for v in assets.values()):
        raise LayaContextError('saved Laya assets differ')
    expected = value['expected']
    if (not isinstance(expected, dict) or set(expected) != {'generation','unit_sha256','env_sha256'}
            or any(re.fullmatch(r'[0-9a-f]{64}', v) is None for v in expected.values())):
        raise LayaContextError('saved installed generation differs')
    export = value['source_export']
    if not isinstance(export, dict) or set(export) != {'directory','files','manifest'}:
        raise LayaContextError('saved exported source differs')
    _identity(export['directory'], 0o700, directory=True)
    if (not isinstance(export['files'], dict) or set(export['files']) != set(ASSETS) | {'source.json'}
            or not isinstance(export['manifest'],dict)
            or type(export['manifest'].get('old_has_decisions')) is not bool
            or export['manifest'] != {'sha':failed_sha, 'old_sha':production_sha, 'old_has_decisions':True, 'files':assets}):
        raise LayaContextError('saved source manifest differs')
    for name, identity in export['files'].items():
        _identity(identity, 0o400)
        if name in assets and identity['sha256'] != assets[name]:
            raise LayaContextError('saved source hash differs')
    # Producer uses json.dump(sort_keys=True) default spacing, without newline.
    if export['files']['source.json']['sha256'] != hashlib.sha256(json.dumps(export['manifest'], sort_keys=True).encode()).hexdigest():
        raise LayaContextError('saved source JSON identity differs')
    _identity(value['receipt'], 0o600)
    _identity(value['production_success'], 0o600)
    # Writer JSON formatting is separately validated live and canonical; do not
    # manufacture a raw-success-byte digest from an assumed serialization here.
    files = value['files']
    if not isinstance(files, dict) or set(files) != {'unit','env','generation','assets','models'}:
        raise LayaContextError('saved installed files differ')
    _identity(files['unit'], 0o644)
    _identity(files['env'], 0o640, gid=None)
    _identity(files['generation'], 0o755, directory=True)
    if (files['unit']['sha256'] != expected['unit_sha256'] or files['env']['sha256'] != expected['env_sha256']
            or not isinstance(files['assets'], dict) or set(files['assets']) != set(ASSETS)):
        raise LayaContextError('saved installed files unbound')
    for name, identity in files['assets'].items():
        _identity(identity, 0o644)
        if identity['sha256'] != assets[name]:
            raise LayaContextError('saved generation source differs')
    manifest = value['model_manifest']
    if (not isinstance(manifest, dict) or set(manifest) != {'repository','revision','files'}
            or manifest['repository'] != 'convaiinnovations/laya'
            or re.fullmatch(r'[0-9a-f]{40}', manifest['revision']) is None
            or not isinstance(manifest['files'], dict) or not manifest['files']
            or not isinstance(files['models'], dict) or set(files['models']) != set(manifest['files'])):
        raise LayaContextError('saved model manifest differs')
    for name, metadata in manifest['files'].items():
        if (not isinstance(name,str) or re.fullmatch(r'[A-Za-z0-9_./-]+',name) is None or '..' in Path(name).parts
                or name.startswith('/') or not isinstance(metadata,dict) or set(metadata) != {'sha256','bytes'}
                or type(metadata['bytes']) is not int or not 0 < metadata['bytes'] <= 1_000_000_000
                or re.fullmatch(r'[0-9a-f]{64}',metadata['sha256']) is None):
            raise LayaContextError('saved model metadata differs')
        _identity(files['models'][name], 0o644)
        if files['models'][name]['sha256'] != metadata['sha256']:
            raise LayaContextError('saved model hash differs')
    chronology = value['chronology']
    if (not isinstance(chronology,dict) or set(chronology) != {'receipt','production_success','unit','env','generation','assets','models'}
            or not isinstance(chronology['assets'],dict) or set(chronology['assets']) != set(ASSETS)
            or not isinstance(chronology['models'],dict) or set(chronology['models']) != set(manifest['files'])):
        raise LayaContextError('saved Laya chronology differs')
    stamps = [chronology[key] for key in ('receipt','production_success','unit','env','generation')]
    stamps += list(chronology['assets'].values()) + list(chronology['models'].values())
    if any(not isinstance(v,list) or len(v)!=2 or any(type(t)is not int or not 0<t<lease_ns for t in v) for v in stamps):
        raise LayaContextError('saved Laya evidence did not predate lease')
    if max(chronology['receipt']) >= min(chronology['production_success']):
        raise LayaContextError('saved installed origin chronology differs')
    services = value['services']
    keys = {'ActiveState','SubState','MainPID','NRestarts','FragmentPath','DropInPaths','User','Group','UnitFileState',
            'NeedDaemonReload','ActiveEnterTimestampMonotonic','ControlGroup','WorkingDirectory','EnvironmentFiles',
            'ExecStart','processes','boot_id'}
    generation = str(BASE / 'generations' / expected['generation'])
    if (not isinstance(services,dict) or set(services) != keys
            or any(services.get(k) != v for k,v in {
                'ActiveState':'active','SubState':'running','NRestarts':'0','DropInPaths':'','User':'reva-laya',
                'Group':'reva-laya','UnitFileState':'enabled','NeedDaemonReload':'no',
                'FragmentPath':str(UNIT),'WorkingDirectory':generation,
                'EnvironmentFiles':str(ENV)+' (ignore_errors=no)',
                'ExecStart':f'path={generation}/venv/bin/python\nargv[]={generation}/venv/bin/python -I {generation}/serve.py\nignore_errors=no'}.items())
            or re.fullmatch(r'[1-9][0-9]*', services['MainPID']) is None
            or services['processes'].keys() != {services['MainPID']}
            or re.fullmatch(r'[0-9]+',services['ActiveEnterTimestampMonotonic']) is None
            or re.fullmatch(r'[0-9]+',services['processes'][services['MainPID']]) is None
            or re.fullmatch(r'[0-9a-f-]{36}',services['boot_id']) is None
            or services['ControlGroup'] != '/system.slice/reva-laya.service'):
        raise LayaContextError('saved Laya process binding differs')
    boot, ticks = value['boot_seconds'], value['ticks_per_second']
    if (boot+int(services['ActiveEnterTimestampMonotonic'])/1_000_000 >= lease_ns/1_000_000_000-60
            or boot+int(services['processes'][services['MainPID']])/ticks >= lease_ns/1_000_000_000-60):
        raise LayaContextError('saved Laya process did not predate lease')
    return value


def validate_history(bootstrap, source, value):
    """Bind saved hashes to immutable canonical code only; never read live state."""
    failed = bootstrap.canonical_source(value['failed_sha'])
    old = bootstrap.canonical_source(value['production_sha'])
    origin = bootstrap.canonical_source(value['origin_sha'])
    assets = {}
    source_bytes = {}
    for name in ASSETS:
        path = failed / 'infra/laya' / name
        bootstrap.secure(path)
        raw = path.read_bytes()
        for root in (old, origin, Path(source)):
            bootstrap.secure(root / 'infra/laya' / name)
        if any((root / 'infra/laya' / name).read_bytes() != raw for root in (old, origin, Path(source))):
            raise LayaContextError('historical Laya source binding differs')
        source_bytes[name] = raw
        assets[name] = hashlib.sha256(raw).hexdigest()
    if value['assets'] != assets or _object(source_bytes['model-manifest.json']) != value['model_manifest']:
        raise LayaContextError('historical asset manifest differs')
    generation = hashlib.sha256(b''.join(name.encode()+b'\0'+source_bytes[name] for name in ASSETS)).hexdigest()
    unit = source_bytes['reva-laya.service.in'].decode().replace('@GENERATION@', str(BASE / 'generations' / generation)).encode()
    witness = old / 'backend/app/config.py'
    bootstrap.secure(witness)
    raw = witness.read_bytes()
    if (hashlib.sha256(raw).hexdigest() != value['old_decision_witness']['sha256']
            or not re.search(rb'decision_provider|DECISION_PROVIDER|decide_route|/v1/systemone|127[.]0[.]0[.]1:8092',raw)
            or value['expected']['generation'] != generation
            or value['expected']['unit_sha256'] != hashlib.sha256(unit).hexdigest()):
        raise LayaContextError('historical installed generation differs')
