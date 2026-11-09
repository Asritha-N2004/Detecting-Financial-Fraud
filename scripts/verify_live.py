"""Exercise a deployed app using a fresh synthetic-only verification workspace.

Creates one disposable account and assessment. Credentials/tokens stay in memory.
"""
import argparse
import secrets
import time
from uuid import uuid4
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    args = parser.parse_args()
    with httpx.Client(base_url=args.url.rstrip('/') + '/api/v1', timeout=90) as client:
        health = client.get('/health')
        health.raise_for_status()
        assert health.json()['worker_enabled'] is False
        print('API and PostgreSQL health: passed', flush=True)
        credentials = {'email': f'deploy-{uuid4().hex}@example.invalid', 'password': secrets.token_urlsafe(30)}
        response = client.post('/auth/register', json={**credentials, 'organization': 'Deployment verification (synthetic only)'})
        response.raise_for_status()
        response = client.post('/auth/login', json=credentials)
        response.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
        print('Registration and sign-in: passed', flush=True)
        response = client.post('/demo/healthy')
        response.raise_for_status()
        assessment = response.json()['id']
        for _ in range(90):
            response = client.get(f'/assessments/{assessment}')
            response.raise_for_status()
            row = response.json()
            if row['status'] in ('completed', 'completed_with_warnings', 'failed'):
                break
            time.sleep(2)
        assert row['status'] in ('completed', 'completed_with_warnings'), f"Assessment did not complete: {row['status']}"
        job = client.get(f'/assessments/{assessment}/job')
        job.raise_for_status()
        assert job.json()['status'] == 'succeeded'
        for endpoint in ('agents', 'reflections', 'explanations', 'audit', 'sensitivity'):
            client.get(f'/assessments/{assessment}/{endpoint}').raise_for_status()
        client.post(f'/assessments/{assessment}/stress-tests', json={'scenario': 'combined_adverse'}).raise_for_status()
        print(f"Worker assessment: completed; score={row['overall_score']}; job=succeeded", flush=True)
        print('Persisted agents/reflections/explanations/audit/sensitivity and stress API: passed', flush=True)


if __name__ == '__main__':
    main()
