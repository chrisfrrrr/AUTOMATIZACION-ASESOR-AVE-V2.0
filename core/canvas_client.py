from __future__ import annotations
import requests
from urllib.parse import urljoin
from typing import Any, Dict, List, Optional

class CanvasAPIError(Exception):
    pass

class CanvasClient:
    def __init__(self, base_url: str, token: str, timeout: int = 45):
        self.base_url = base_url.rstrip('/') + '/'
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token.strip()}',
            'Accept': 'application/json'
        })

    def _url(self, endpoint: str) -> str:
        endpoint = endpoint.lstrip('/')
        if endpoint.startswith('api/v1/'):
            return urljoin(self.base_url, endpoint)
        return urljoin(self.base_url, 'api/v1/' + endpoint)

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, paginate: bool = True) -> Any:
        url = self._url(endpoint)
        params = dict(params or {})
        params.setdefault('per_page', 100)
        if not paginate:
            r = self.session.get(url, params=params, timeout=self.timeout)
            return self._handle(r)
        results: List[Any] = []
        first = True
        while url:
            r = self.session.get(url, params=params if first else None, timeout=self.timeout)
            data = self._handle(r)
            if isinstance(data, list):
                results.extend(data)
            else:
                return data
            url = r.links.get('next', {}).get('url')
            first = False
        return results

    @staticmethod
    def _handle(response: requests.Response) -> Any:
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise CanvasAPIError(f'Canvas respondió {response.status_code}: {detail}')
        if not response.text:
            return None
        return response.json()

    def whoami(self) -> Dict[str, Any]:
        return self.get('users/self', paginate=False)

    def courses(self) -> List[Dict[str, Any]]:
        return self.get('courses', params={'enrollment_state': 'active', 'include[]': ['term']})

    def sections(self, course_id: int | str) -> List[Dict[str, Any]]:
        return self.get(f'courses/{course_id}/sections')

    def enrollments(self, course_id: int | str, section_id: Optional[int | str] = None) -> List[Dict[str, Any]]:
        endpoint = f'sections/{section_id}/enrollments' if section_id else f'courses/{course_id}/enrollments'
        return self.get(endpoint, params={
            'type[]': 'StudentEnrollment',
            'state[]': 'active',
            'include[]': ['user', 'avatar_url']
        })

    def assignments(self, course_id: int | str) -> List[Dict[str, Any]]:
        return self.get(f'courses/{course_id}/assignments', params={
            'include[]': ['due_dates', 'all_dates'],
            'order_by': 'due_at'
        })

    def submissions(self, course_id: int | str) -> List[Dict[str, Any]]:
        # Devuelve entregas de todos los estudiantes con la tarea incluida.
        return self.get(f'courses/{course_id}/students/submissions', params={
            'student_ids[]': 'all',
            'include[]': ['assignment', 'user'],
            'grouped': False
        })
