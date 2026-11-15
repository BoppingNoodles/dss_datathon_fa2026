import random

from src.phoenix import job_evidence, ranking
from src.phoenix.models import Job, ServiceLocation, UserProfile
from src.phoenix.normalization import haversine_miles
from src.phoenix.spatial import ServiceIndex


def test_posting_extraction_is_reused_but_updated_content_is_reparsed(monkeypatch):
    job_evidence._posting_evidence.cache_clear()
    original = job_evidence.with_qualification_evidence
    parsed = []

    def tracked(job):
        parsed.append(job.description)
        return original(job)

    monkeypatch.setattr(job_evidence, 'with_qualification_evidence', tracked)
    job = Job(job_id='posting', title='Warehouse associate', company='Example', city='Oakland',
              location_text='Oakland, CA', description='High school diploma required.')
    first = job_evidence.prepared_job(job)
    first.requirements.clear()
    assert job_evidence.prepared_job(job).requirements
    changed = job.model_copy(update={'description': "Bachelor's degree required."})
    assert any(requirement.value == 'bachelor' for requirement in job_evidence.prepared_job(changed).requirements)
    assert len(parsed) == 2
    assert job.requirements == []
    job_evidence._posting_evidence.cache_clear()


def test_shared_posting_cache_never_reuses_a_persons_qualification_answers():
    job = Job(job_id='shared', title='Warehouse associate', company='Example', city='Oakland',
              location_text='Oakland, CA', description="Bachelor's degree required.")
    ready = UserProfile(location='Oakland', priority_need='work', education={'level': 'bachelor'})
    preparing = ready.model_copy(update={'education': ready.education.model_copy(update={'level': 'high_school'})})
    assert not ranking.rank_jobs([job], ready)[0].qualification_gaps
    assert ranking.rank_jobs([job], preparing)[0].qualification_gaps
    assert not ranking.rank_jobs([job], ready)[0].qualification_gaps


def test_vectorized_proximity_counts_match_scalar_distance_checks():
    rng = random.Random(2048)
    services = [ServiceLocation(place_id=f'service-{index}', service_family=f'family-{index % 4}',
        latitude=37.8 + rng.uniform(-.08, .08), longitude=-122.27 + rng.uniform(-.08, .08),
        permanently_closed=index % 17 == 0, temporarily_closed=index % 19 == 0) for index in range(500)]
    index = ServiceIndex(services + [services[1]])
    active = [service for service in services if not service.permanently_closed and not service.temporarily_closed]
    for radius in (.2, 1, 3):
        for _ in range(12):
            lat, lon = 37.8 + rng.uniform(-.07, .07), -122.27 + rng.uniform(-.07, .07)
            expected = {family: sum(service.service_family == family and
                haversine_miles(lat, lon, service.latitude, service.longitude) <= radius for service in active)
                for family in index.families}
            assert index.counts(lat, lon, radius) == expected
    assert ServiceIndex([]).counts(37.8, -122.27, 1) == {}
