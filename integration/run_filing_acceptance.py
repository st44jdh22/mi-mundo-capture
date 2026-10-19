"""Executable attended A58/Head Chef synthetic acceptance; no external services."""
import json
from test_filing_service import FilingTests, Projection, specification
from filing.adapters import PostOfficeStatusAdapter


def main():
    fixture=FilingTests()
    fixture.setUp()
    try:
        fixture.submit()
        fixture.transport.mode='transient'
        fixture.run_job()
        projection=Projection();projection.fail_on_error=True
        for _ in range(30):
            if not fixture.s.flush_reporting(PostOfficeStatusAdapter(projection)):break
        first=fixture.status()
        fixture.reopen();fixture.now+=30
        fixture.transport.mode=None;fixture.run_job()
        projection.fail_on_error=False
        for _ in range(50):
            if not fixture.s.flush_reporting(PostOfficeStatusAdapter(projection)):break
        a58=fixture.status()
        fixture.spec=specification(chef=True)
        fixture.submit();fixture.run_job()
        chef=fixture.status()
        assert first['state']=='RETRY PENDING'
        assert a58['state']=='VERIFIED COMPLETE' and not a58['reporting_pending']
        assert chef['state']=='VERIFIED COMPLETE' and len(chef['targets'])==3
        print(json.dumps({'mode':'LOCAL_SYNTHETIC_ONLY', 'a58_after_upload_and_logging_failure':first,
            'a58_recovered':a58,'chef_simulated_records_verified':chef,
            'real_A58_reuploaded':False,'real_inventory_writes':0,'external_calls':0},indent=2))
    finally:fixture.tearDown()


if __name__=='__main__':main()
