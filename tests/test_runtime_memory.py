from pathlib import Path
import json,os,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_core as core
import runtime_memory as memory
from memory_guard import evaluate_guard
from test_memory_guard import snapshot,M
from test_acquisition import Response

class RuntimeMemoryTests(unittest.TestCase):
    def test_reserve_and_unknown_budget_are_distinct(self):
        cfg=core.read(core.ROOT/'config/cv-low-memory.json')
        guard=evaluate_guard(snapshot(),cfg,reserve_mib=128)
        self.assertFalse(guard['abort']);self.assertEqual(guard['headroomBasis'],'conservative_working_set_estimate')
        self.assertLess(guard['headroomToSkillRawCeilingBytes'],128*M);self.assertGreater(guard['headroomForStageBytes'],128*M)
        self.assertFalse(evaluate_guard(snapshot(usage=840),cfg,reserve_mib=128)['abort'])
        g=evaluate_guard({'status':'unavailable'},cfg,reserve_mib=128)
        self.assertFalse(g['headroomKnown']);self.assertNotIn('headroomToSkillRawCeilingBytes',g)
    def test_cache_advice_is_scoped_and_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'media').mkdir();(root/'acquisition').mkdir()
            video=root/'media/source-video.mp4';video.write_bytes(b'video')
            outside=root/'outside.mp4';outside.write_bytes(b'outside')
            (root/'media/link.mp4').symlink_to(outside)
            (root/'media/dependency.so').write_bytes(b'binary')
            with patch.object(os,'posix_fadvise',create=True,side_effect=OSError(22,'unsupported')) as advise,patch.object(os,'POSIX_FADV_DONTNEED',4,create=True):
                result=memory.release_completed(root,'test')
            self.assertEqual(advise.call_count,1);self.assertEqual(result['advisedBytes'],0)
            self.assertEqual(result['errors'][0]['errno'],22);self.assertEqual(video.read_bytes(),b'video')
    def test_download_receipt_hash_matches_stream_and_closes_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'media/source-video.mp4';receipt=root/'receipt.json'
            response=Response([b'abc',b'def']);session=type('S',(),{'get':lambda *a,**kw:response})()
            core.download('https://example.test/video',target,max_bytes=20,session=session,receipt_path=receipt,receipt_root=root)
            self.assertEqual(core.read(receipt),core.artifact(target,root));self.assertTrue(response.closed)
    def test_report_uses_observed_peak_and_reports_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=[{'time':i,'attemptId':'a','memoryEstimate':{'rawUsageBytes':v,'workingSetEstimateBytes':v-10,'memoryStat':{'total_cache':v//2,'total_rss':v//3}}} for i,v in enumerate((100,500,200))]
            (root/'resources.ndjson').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            summary=core.resource_summary(root)
            self.assertEqual(summary['peaks']['rawUsageBytes'],500);self.assertEqual(summary['peaks']['cacheBytes'],250)
            self.assertNotIn('processTreeSampledRssBytes',summary['peaks'])

    def test_owned_input_sha256_advice_is_bounded_aligned_and_fsync_once(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'video.mp4';raw=b'x'*(2*1024*1024+37);path.write_bytes(raw)
            events=[]
            with patch.object(os,'fsync',side_effect=lambda fd:events.append(('sync',))),patch.object(os,'posix_fadvise',create=True,side_effect=lambda fd,offset,length,policy:events.append(('advice',offset,length))),patch.object(os,'POSIX_FADV_DONTNEED',4,create=True):
                sha=memory.digest_owned(path,owner_root=root,log_root=root,stage='hash_test')
            self.assertEqual(sha,hashlib.sha256(raw).hexdigest());self.assertEqual(events[0],('sync',))
            self.assertEqual(sum(e[0]=='sync' for e in events),1)
            self.assertEqual(events[1:], [('advice',0,1024*1024),('advice',1024*1024,1024*1024),('advice',0,0)])
            row=json.loads((root/'cache-advice.ndjson').read_text().splitlines()[-1])
            self.assertEqual(row['hashedBytes'],len(raw));self.assertEqual(row['sha256'],sha)
            self.assertEqual(row['initialFileStat'],row['finalFileStat']);self.assertEqual(path.read_bytes(),raw)

    def test_owned_hash_rejects_file_parent_and_owner_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner=root/'owner';owner.mkdir();outside=root/'outside';outside.mkdir();(outside/'v.mp4').write_bytes(b'outside')
            (owner/'link.mp4').symlink_to(outside/'v.mp4');(owner/'nested').symlink_to(outside,target_is_directory=True)
            alias=root/'alias';alias.symlink_to(outside,target_is_directory=True)
            with patch.object(os,'posix_fadvise',create=True) as advise,patch.object(os,'POSIX_FADV_DONTNEED',4,create=True):
                for path,boundary in [(owner/'link.mp4',owner),(owner/'nested/v.mp4',owner),(alias/'v.mp4',alias)]:
                    with self.assertRaises(core.ProbeError):memory.digest_owned(path,owner_root=boundary,log_root=root,stage='unsafe_hash')
                result=memory.release_owned(root,'unsafe_owner',alias,[alias/'v.mp4'])
            advise.assert_not_called();self.assertEqual(result['attemptedFiles'],0)

    def test_owned_hash_unsupported_advice_preserves_complete_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'v.mp4';path.write_bytes(b'a'*1048579)
            with patch.object(os,'posix_fadvise',create=True,side_effect=OSError(22,'unsupported')) as advise,patch.object(os,'POSIX_FADV_DONTNEED',4,create=True):
                sha=memory.digest_owned(path,owner_root=root,log_root=root,stage='unsupported')
            self.assertEqual(sha,hashlib.sha256(path.read_bytes()).hexdigest());self.assertEqual(advise.call_count,1)
            row=json.loads((root/'cache-advice.ndjson').read_text().splitlines()[-1]);self.assertEqual(row['errors'][0]['errno'],22)

    def test_release_item_uses_only_completed_attempt_receipt_and_records_gc(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);attempt=root/'cv/current';old=root/'cv/old';snapshot_root=root/'snapshot'
            core.write(attempt/'shots.json',{'shots':[]});core.write(old/'private.json',{})
            core.write(attempt/'receipt.json',{'processCleanup':{'status':'completed'},'artifacts':[core.artifact(attempt/'shots.json',attempt)]})
            core.write(snapshot_root/'report/report.json',{});core.write(snapshot_root/'report/receipt.json',{})
            original=memory.release_owned;paths=[]
            def track(log_root,stage,owner,listed):
                paths.extend(Path(p) for p in listed);return original(log_root,stage,owner,listed)
            with patch.object(memory,'release_owned',side_effect=track),patch.object(memory.gc,'collect',return_value=3):
                result=memory.release_item(root,'item_complete',attempt_id='current',report_root=snapshot_root)
            self.assertIn(attempt/'shots.json',paths);self.assertNotIn(old/'private.json',paths)
            self.assertEqual(result['pythonGc']['collectedObjects'],3)
            core.write(attempt/'receipt.json',{'processCleanup':{'status':'unconfirmed'},'artifacts':[core.artifact(attempt/'shots.json',attempt)]})
            paths.clear()
            with patch.object(memory,'release_owned',side_effect=track):memory.release_item(root,'unsafe',attempt_id='current')
            self.assertNotIn(attempt/'shots.json',paths)

    def test_owned_hash_detects_replaced_path_during_complete_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'v.mp4';path.write_bytes(b'original'*150000);replacement=root/'replacement';replacement.write_bytes(b'new')
            original=os.read;changed=False
            def swapped(fd,size):
                nonlocal changed
                data=original(fd,size)
                if not changed:changed=True;os.replace(replacement,path)
                return data
            with patch.object(os,'read',side_effect=swapped):
                with self.assertRaises(core.ProbeError) as error:memory.digest_owned(path,owner_root=root,log_root=root,stage='changed_hash')
            self.assertEqual(error.exception.code,'artifact_changed');self.assertEqual(path.read_bytes(),b'new')
