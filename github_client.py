import base64
import json
import requests


class GitHubApiError(Exception):
    pass


class GitHubClient:
    def __init__(self, token, user_agent='GitHubGuiEditor/1.0'):
        self.token = token
        self.base_url = 'https://api.github.com'
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': user_agent,
            'X-GitHub-Api-Version': '2022-11-28',
        })

    def _raise_for_status(self, resp):
        if 200 <= resp.status_code < 300:
            return
        try:
            detail = resp.json()
        except Exception:
            detail = {'message': resp.text}
        msg = detail.get('message', 'GitHub API error')
        raise GitHubApiError(f'{resp.status_code}: {msg}')

    def get_user(self):
        r = self.session.get(f'{self.base_url}/user')
        self._raise_for_status(r)
        return r.json()

    def list_repos(self, affiliation='owner,collaborator,organization_member', per_page=100):
        # We keep paging simple but correct.
        repos = []
        page = 1
        while True:
            r = self.session.get(
                f'{self.base_url}/user/repos',
                params={
                    'per_page': per_page,
                    'page': page,
                    'sort': 'updated',
                    'direction': 'desc',
                    'affiliation': affiliation,
                },
            )
            self._raise_for_status(r)
            batch = r.json()
            repos.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return repos

    def list_branches(self, owner, repo, per_page=100):
        branches = []
        page = 1
        while True:
            r = self.session.get(
                f'{self.base_url}/repos/{owner}/{repo}/branches',
                params={'per_page': per_page, 'page': page},
            )
            self._raise_for_status(r)
            batch = r.json()
            branches.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return branches

    def get_repo(self, owner, repo):
        r = self.session.get(f'{self.base_url}/repos/{owner}/{repo}')
        self._raise_for_status(r)
        return r.json()

    def get_contents(self, owner, repo, path='', ref=None):
        # Returns list for directories, dict for files.
        url = f'{self.base_url}/repos/{owner}/{repo}/contents/{path}'.rstrip('/')
        if url.endswith('/contents'):
            url = f'{self.base_url}/repos/{owner}/{repo}/contents'

        params = {}
        if ref:
            params['ref'] = ref

        r = self.session.get(url, params=params)
        self._raise_for_status(r)
        return r.json()

    def get_file_text(self, owner, repo, path, ref=None):
        obj = self.get_contents(owner, repo, path, ref)
        if not isinstance(obj, dict) or obj.get('type') != 'file':
            raise GitHubApiError('Not a file')

        content_b64 = obj.get('content', '')
        if obj.get('encoding') != 'base64':
            raise GitHubApiError('Unexpected file encoding')

        raw = base64.b64decode(content_b64)
        try:
            return raw.decode('utf-8', errors='replace'), obj
        except Exception:
            return raw.decode('utf-8', errors='replace'), obj

    def create_repo(self, name, private=True, description='', auto_init=True):
        payload = {
            'name': name,
            'private': bool(private),
            'description': description or '',
            'auto_init': bool(auto_init),
        }
        r = self.session.post(f'{self.base_url}/user/repos', json=payload)
        self._raise_for_status(r)
        return r.json()

    def put_file(self, owner, repo, path, content_bytes, message, branch=None, sha=None):
        payload = {
            'message': message,
            'content': base64.b64encode(content_bytes).decode('utf-8'),
        }
        if branch:
            payload['branch'] = branch
        if sha:
            payload['sha'] = sha

        r = self.session.put(f'{self.base_url}/repos/{owner}/{repo}/contents/{path.lstrip("/")}', json=payload)
        self._raise_for_status(r)
        return r.json()

    def delete_file(self, owner, repo, path, message, sha, branch=None):
        payload = {
            'message': message,
            'sha': sha,
        }
        if branch:
            payload['branch'] = branch

        r = self.session.delete(f'{self.base_url}/repos/{owner}/{repo}/contents/{path.lstrip("/")}', json=payload)
        self._raise_for_status(r)
        return r.json()
