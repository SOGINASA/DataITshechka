import re

from jsonschema import Draft202012Validator
from openapi_spec_validator import validate


def test_openapi_matches_routes_and_real_responses(app, client, evaluation):
    spec = client.get('/api/openapi.json').json
    validate(spec)
    documented = {(path, method.upper()) for path, methods in spec['paths'].items() for method in methods}
    actual = {(re.sub(r'<([^>]+)>', r'{\1}', rule.rule), method)
              for rule in app.url_map.iter_rules() if rule.rule.startswith('/api')
              for method in rule.methods - {'OPTIONS', 'HEAD'}}
    assert actual == documented
    paths = {
        '/api': '/api', '/api/health': '/api/health', '/api/ready': '/api/ready',
        '/api/conversations': '/api/conversations', '/api/checklists': '/api/checklists', '/api/stats': '/api/stats',
        '/api/conversations/{conversation_id}': '/api/conversations/' + evaluation['conversation_id'],
        '/api/conversations/{conversation_id}/evaluations': f'/api/conversations/{evaluation["conversation_id"]}/evaluations',
        '/api/checklists/{checklist_id}': '/api/checklists/' + evaluation['checklist_id'],
        '/api/evaluations/{evaluation_id}': '/api/evaluations/' + evaluation['id'],
        '/api/evaluations/{evaluation_id}/reviews': f'/api/evaluations/{evaluation["id"]}/reviews',
        '/api/evaluations/{evaluation_id}/export': f'/api/evaluations/{evaluation["id"]}/export',
    }
    for template, path in paths.items():
        response = client.get(path)
        assert response.status_code == 200
        schema = spec['paths'][template]['get']['responses']['200']['content']['application/json']['schema']
        Draft202012Validator({**schema, 'components': spec['components']}).validate(response.json)
    post_url = f'/api/evaluations/{evaluation["id"]}/reviews'
    response = client.post(post_url, json={'expected_revision': 1, 'reviewer': 'Test', 'comment': 'Reviewed',
                                         'overrides': [{'criterion_id': 'resolution', 'status': 'pass', 'explanation': 'Resolved'}]})
    assert response.status_code == 201
    schema = spec['paths']['/api/evaluations/{evaluation_id}/reviews']['post']['responses']['201']['content']['application/json']['schema']
    Draft202012Validator({**schema, 'components': spec['components']}).validate(response.json)
    for path in ('/api/missing', '/api/conversations?per_page=0'):
        Draft202012Validator({'$ref': '#/components/schemas/Error', 'components': spec['components']}).validate(client.get(path).json)
