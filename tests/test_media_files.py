import hashlib
import io
import zipfile
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation_integrations import media_files as files
from automation_integrations import media_runtime as runtime


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir(mode=0o700)
        self.state = self.home / 'state'
        self.state.mkdir(mode=0o700)
        self.cache = self.home / '.hermes' / 'image_cache'
        self.cache.mkdir(parents=True, mode=0o700)
        self.audio = self.home / '.hermes' / 'audio_cache'
        self.audio.mkdir(mode=0o700)
        self.config = {'os_home': str(self.home), 'state_dir': str(self.state)}

    def asset(self, name='image.png', data=b'\x89PNG\r\n\x1a\nimage'):
        path = self.cache / name
        path.write_bytes(data)
        return path

    def test_prepare_and_restart_read_exact_image(self):
        path = self.asset()
        prepared = files.prepare_upload({'path':str(path)}, self.config, 'fal')
        self.assertEqual(prepared['content_type'],'image/png')
        self.assertEqual(prepared['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(prepared['bytes'],path.stat().st_size)
        self.assertEqual(len(prepared['_stat']),5)
        reloaded = json.loads(json.dumps(prepared))
        self.assertEqual(files.read_upload(reloaded,self.config,'fal'),path.read_bytes())

    def test_text_json_zip_types_and_filename_mime_validation(self):
        for name, data, mime in [('sample.txt',b'hello','text/plain'),
                                 ('table.json',b'{"rows":[1,2]}','application/json'),
                                 ('rows.csv',b'name,value\none,1','text/csv'),
                                 ('archive.zip',b'PK\x05\x06'+b'\0'*18,'application/zip')]:
            with self.subTest(name=name):
                path=self.asset(name,data)
                prepared=files.prepare_upload({'path':str(path)},self.config,'inference')
                self.assertEqual(prepared['content_type'],mime)
        path=self.asset()
        for params in ({'path':str(path),'content_type':'text/plain'},
                       {'path':str(path),'filename':'photo.txt'},
                       {'path':str(path),'filename':'../photo.png'}):
            with self.assertRaises(runtime.MediaError):files.prepare_upload(params,self.config,'fal')

    def test_reject_file_and_ancestor_symlinks_even_inside_root(self):
        target=self.asset()
        linked=self.cache/'link.png';linked.symlink_to(target)
        with self.assertRaisesRegex(runtime.MediaError,'symlink'):
            files.prepare_upload({'path':str(linked)},self.config,'fal')
        directory=self.cache/'actual';directory.mkdir();(directory/'a.txt').write_text('hello')
        alias=self.cache/'alias';alias.symlink_to(directory,target_is_directory=True)
        with self.assertRaisesRegex(runtime.MediaError,'symlink'):
            files.prepare_upload({'path':str(alias/'a.txt')},self.config,'fal')

    def test_replace_after_prepare_same_size_or_same_bytes_is_rejected(self):
        path=self.asset('sample.txt',b'one')
        prepared=files.prepare_upload({'path':str(path)},self.config,'fal')
        path.write_bytes(b'two')
        with self.assertRaisesRegex(runtime.MediaError,'changed_since_prepare'):
            files.read_upload(prepared,self.config,'fal')
        prepared=files.prepare_upload({'path':str(path)},self.config,'fal')
        path.unlink();path.write_bytes(b'two')
        with self.assertRaisesRegex(runtime.MediaError,'changed_since_prepare'):
            files.read_upload(prepared,self.config,'fal')

    def test_no_arbitrary_hermes_directory_or_path_escape(self):
        secret=self.home/'.hermes'/'session.txt';secret.write_text('secret')
        sibling=self.home/'.hermes'/'image_cache_other';sibling.mkdir();(sibling/'sample.txt').write_text('secret')
        for path in (str(secret),str(sibling/'sample.txt'),str(self.cache/'../session.txt'),'relative.txt'):
            with self.subTest(path=path),self.assertRaises(runtime.MediaError):
                files.prepare_upload({'path':path},self.config,'inference')
        with self.assertRaisesRegex(runtime.MediaError,'unsafe_hermes'):
            files.prepare_upload({'path':str(secret)},{**self.config,'media_upload_roots':[str(self.home/'.hermes')]},'fal')
        with self.assertRaisesRegex(runtime.MediaError,'unsafe_media_upload_root'):
            files.prepare_upload({'path':str(secret)},{**self.config,'media_upload_roots':[str(self.home)]},'fal')

    def test_configured_asset_directory_replaces_defaults(self):
        root=self.home/'uploads';root.mkdir();path=root/'table.json';path.write_text('{"rows": []}')
        config={**self.config,'media_upload_roots':[str(root)]}
        self.assertEqual(files.prepare_upload({'path':str(path)},config,'fal')['filename'],'table.json')
        image=self.asset()
        with self.assertRaisesRegex(runtime.MediaError,'outside_allowed_roots'):
            files.prepare_upload({'path':str(image)},config,'fal')

    def test_all_default_roots_and_artifact_manifests_are_private(self):
        for root in (self.audio,self.home/'vaults'/'Automation'/'80_Файлы',
                     self.state/'media'/'artifacts',self.state/'media'/'media-artifacts'):
            root.mkdir(mode=0o700,parents=True,exist_ok=True)
            path=root/'image.png';path.write_bytes(b'\x89PNG\r\n\x1a\nimage')
            self.assertEqual(files.prepare_upload({'path':str(path)},self.config,'fal')['bytes'],13)
        manifest=self.state/'media'/'media-artifacts'/('a'*64+'.json')
        manifest.write_text('{"source_url":"https://cloud.inference.sh/private?signature=secret"}')
        with self.assertRaisesRegex(runtime.MediaError,'manifest_upload_forbidden'):
            files.prepare_upload({'path':str(manifest)},self.config,'inference')

    def test_known_artifact_root_can_be_inside_hermes_state(self):
        state=self.home/'.hermes'/'integration-state'
        root=state/'media'/'media-artifacts';root.mkdir(parents=True,mode=0o700)
        path=root/'image.png';path.write_bytes(b'\x89PNG\r\n\x1a\nimage')
        config={**self.config,'state_dir':str(state)}
        self.assertEqual(files.prepare_upload({'path':str(path)},config,'fal')['filename'],'image.png')

    def test_secret_extensions_names_content_and_nonregular_files_rejected(self):
        for name,data in [('key.pem',b'fake'),('.env',b'KEY=x'),('credentials.json',b'{}'),
                          ('auth.json',b'{}'),('data.json',b'{"private_key":"secret"}'),
                          ('data.txt',b'OPENAI_API_KEY=secret'),('renamed.png',b'private data'),
                          ('data.txt',b'-----BEGIN PRIVATE KEY-----\nsecret')]:
            path=self.asset(name,data)
            with self.subTest(name=name),self.assertRaises(runtime.MediaError):
                files.prepare_upload({'path':str(path)},self.config,'fal')
        fifo=self.cache/'pipe.txt';os.mkfifo(fifo)
        with self.assertRaisesRegex(runtime.MediaError,'requires_regular_file'):
            files.prepare_upload({'path':str(fifo)},self.config,'fal')

    def test_zip_rejects_hidden_secrets_and_traversal_without_extraction(self):
        for entry in ('.env','credentials.json','../escape.png','folder/private.key'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:archive.writestr(entry,b'content')
            path=self.asset('assets.zip',stream.getvalue())
            with self.subTest(entry=entry),self.assertRaises(runtime.MediaError):
                files.prepare_upload({'path':str(path)},self.config,'fal')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:archive.writestr('images/picture.png',b'image')
        path=self.asset('assets.zip',stream.getvalue())
        self.assertEqual(files.prepare_upload({'path':str(path)},self.config,'fal')['content_type'],'application/zip')

    def test_service_size_limits_without_reading_oversized_contents(self):
        path=self.cache/'large.txt'
        with path.open('wb') as handle:handle.truncate(8*1024*1024+1)
        with patch.object(files.os,'read') as reader:
            with self.assertRaisesRegex(runtime.MediaError,'size_out_of_range'):
                files.prepare_upload({'path':str(path)},self.config,'fal')
            reader.assert_not_called()
        with path.open('wb') as handle:handle.truncate(32*1024*1024+1)
        with self.assertRaisesRegex(runtime.MediaError,'size_out_of_range'):
            files.prepare_upload({'path':str(path)},self.config,'inference')

    def test_prepared_metadata_and_roots_revalidated_on_execute(self):
        path=self.asset();prepared=files.prepare_upload({'path':str(path)},self.config,'fal')
        for tamper in ({'bytes':True},{'sha256':'0'*64},{'_stat':[0]*5},{'path':'/etc/passwd'}):
            with self.subTest(tamper=tamper),self.assertRaises(runtime.MediaError):
                files.read_upload({**prepared,**tamper},self.config,'fal')
        new=self.home/'new';new.mkdir()
        with self.assertRaises(runtime.MediaError):files.read_upload(prepared,{**self.config,'media_upload_roots':[str(new)]},'fal')


class ArtifactReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.jobs=runtime.JobStore(self.root)
        self.job,_=self.jobs.prepare('owner-request',{'operation':'upload'},account='owner-account',provider='inference')
        self.artifacts=runtime.ArtifactStore(self.root)
        self.url='https://cloud.inference.sh/private/image.png?signature=signed-value'
        self.view=self.artifacts.register(self.url,self.job['job_id'],metadata={'account':'owner-account'})
        self.ident=self.view['artifact_id']

    def test_nested_references_resolve_without_network_or_input_mutation(self):
        original={'images':['artifact:'+self.ident,{'artifact_id':self.ident}],
                  'prompt':'simple','nested':{'value':3}}
        with patch.object(runtime,'_open_response') as network:
            output=files.resolve_artifact_references(original,self.root,'owner-account')
            network.assert_not_called()
        self.assertEqual(output['images'],[self.url,self.url])
        self.assertEqual(original['images'][0],'artifact:'+self.ident)

    def test_artifact_owner_bound_and_malformed_handles_fail(self):
        with self.assertRaisesRegex(runtime.MediaError,'job_account_mismatch'):
            files.resolve_artifact_references('artifact:'+self.ident,self.root,'other-account')
        for value in ('artifact:../../secret','artifact:bad',{'artifact_id':self.ident,'url':'evil'}):
            with self.assertRaises(runtime.MediaError):files.resolve_artifact_references(value,self.root,'owner-account')

    def test_manifest_tampering_or_symlink_cannot_change_url_or_job(self):
        path=self.artifacts._path(self.ident);row=json.loads(path.read_text())
        row['source_url']='https://cloud.inference.sh/other'
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(runtime.MediaError,'integrity_failed'):
            files.resolve_artifact_references('artifact:'+self.ident,self.root,'owner-account')
        path.unlink();target=self.root/'outside.json';target.write_text(json.dumps(row));path.symlink_to(target)
        with self.assertRaisesRegex(runtime.MediaError,'invalid_artifact_manifest'):
            files.resolve_artifact_references('artifact:'+self.ident,self.root,'owner-account')

    def test_unrelated_json_never_creates_state_directories(self):
        absent=self.root/'absent'
        value={'input':{'prompt':'hello'},'array':[1,True,None]}
        self.assertEqual(files.resolve_artifact_references(value,absent,'owner-account'),value)
        self.assertFalse(absent.exists())


if __name__=='__main__':unittest.main()
