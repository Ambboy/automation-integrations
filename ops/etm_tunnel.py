# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Provision a separate Example Egress -> Kronstadt reverse SOCKS connection, no VPN changes.

Run with system Python on Kronstadt. Commands are fixed; only public host/user keys
cross stdout. The private client key remains on Example Egress (backup enrollment is separate).
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog/tunnel')


def remote(code):
    inner = shlex.join(['ssh', '-F', '/home/operator/.ssh/cloudcli-vpn-admin.conf', 'example-egress-admin',
                        'sudo -n python3 -c ' + shlex.quote(code)])
    p = subprocess.run(['ssh', 'example-hermes', inner], capture_output=True, text=True, timeout=45)
    if p.returncode:
        raise RuntimeError('Example Egress provisioning command failed: ' + p.stderr[-400:])
    return json.loads(p.stdout)


def local(code):
    p = subprocess.run(['sudo', '-n', 'python3', '-c', code], capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError('Kronstadt provisioning command failed: ' + p.stderr[-400:])
    return json.loads(p.stdout)


def main():
    if sys.argv[1:] != ['apply']:
        raise SystemExit('Use apply; see docs for exact rollback of only the new unit and role')
    os.umask(0o077); ROOT.mkdir(mode=0o700, exist_ok=True)
    assert not (ROOT / 'deployed.json').exists(), 'Already provisioned; inspect status instead'
    host_key = Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()[:2]
    result = remote('''import json,subprocess,pwd,os
from pathlib import Path
name='greif-etm-egress'; root=Path('/var/lib/greif-etm-egress')
try: user=pwd.getpwnam(name)
except KeyError:
 subprocess.run(['useradd','--system','--create-home','--home-dir',str(root),'--shell','/usr/sbin/nologin',name],check=True)
 user=pwd.getpwnam(name)
assert user.pw_dir==str(root)
root.mkdir(mode=0o700,exist_ok=True);root.chmod(0o700);os.chown(root,user.pw_uid,user.pw_gid)
key=root/'id_ed25519'
if not key.exists():subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','greif-etm-egress','-f',str(key)],check=True)
key.chmod(0o600);os.chown(key,user.pw_uid,user.pw_gid)
print(json.dumps({'public_key':key.with_suffix('.pub').read_text().strip()}))''')
    public_key = ' '.join(result['public_key'].split()[:2])
    assert public_key.startswith('ssh-ed25519 ')
    sshd = '''AllowUsers greif-etm-tunnel@192.0.2.10
Match User greif-etm-tunnel
    AuthenticationMethods publickey
    PasswordAuthentication no
    AuthorizedKeysFile /etc/ssh/greif-etm-keys/authorized_keys
    AllowTcpForwarding remote
    AllowStreamLocalForwarding no
    PermitListen 127.0.0.1:10929
    GatewayPorts no
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    ForceCommand /bin/false
Match all
'''
    auth = 'from="192.0.2.10",restrict,port-forwarding,permitlisten="127.0.0.1:10929" ' + public_key + '\n'
    result = local('''import json,subprocess,pwd
from pathlib import Path
name='greif-etm-tunnel'
try: user=pwd.getpwnam(name)
except KeyError:subprocess.run(['useradd','--system','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin',name],check=True)
files=''' + repr({'/etc/ssh/sshd_config.d/97-greif-etm-tunnel.conf': sshd,
                '/etc/ssh/greif-etm-keys/authorized_keys': auth}) + '''
for name,content in files.items():
 p=Path(name);p.parent.mkdir(mode=0o755,exist_ok=True)
 if str(p.parent)=='/etc/ssh/greif-etm-keys':p.parent.chmod(0o755)
 if p.exists():assert p.read_text()==content,'Conflicting existing tunnel configuration'
 else:p.write_text(content)
 p.chmod(0o644)
subprocess.run(['/usr/sbin/sshd','-t'],check=True)
subprocess.run(['systemctl','reload','ssh'],check=True)
print(json.dumps({'sshd_valid':True,'sshd_reloaded':True}))''')
    unit = '''[Unit]
Description=Greif ETM Russian egress via Example Egress (reverse SOCKS to Kronstadt)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=greif-etm-egress
Group=greif-etm-egress
ExecStart=/usr/bin/ssh -NT -F /dev/null -i /var/lib/greif-etm-egress/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/var/lib/greif-etm-egress/known_hosts -o UpdateHostKeys=no -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ServerAliveInterval=20 -o ServerAliveCountMax=3 "-oPermitRemoteOpen=ipro.etm.ru:443 www.etm.ru:443 api.ipify.org:443" -R 127.0.0.1:10929 greif-etm-tunnel@192.0.2.11
Restart=always
RestartSec=5
TimeoutStopSec=10
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077

[Install]
WantedBy=multi-user.target
'''
    known = '192.0.2.11 ' + ' '.join(host_key) + '\n'
    result = remote('''import json,subprocess,pwd,os
from pathlib import Path
unit=''' + repr(unit) + '''
known=''' + repr(known) + '''
p=Path('/etc/systemd/system/greif-etm-egress.service')
if p.exists():assert p.read_text()==unit,'Conflicting unit'
else:p.write_text(unit);p.chmod(0o644)
k=Path('/var/lib/greif-etm-egress/known_hosts');k.write_text(known);k.chmod(0o600)
u=pwd.getpwnam('greif-etm-egress');os.chown(k,u.pw_uid,u.pw_gid)
subprocess.run(['systemd-analyze','verify',str(p)],check=True,capture_output=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','greif-etm-egress.service'],check=True,capture_output=True)
print(json.dumps({'enabled':True,'unit':'greif-etm-egress.service'}))''')
    receipt = {'example_egress': result, 'listener': '127.0.0.1:10929', 'transport': 'existing GRE + independent reverse SSH',
               'vpn_changed': False, 'firewall_changed': False, 'allowed_destinations': ['ipro.etm.ru:443', 'www.etm.ru:443', 'api.ipify.org:443']}
    (ROOT / 'deployed.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
