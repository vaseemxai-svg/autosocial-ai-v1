"""
Composition root — the ONE place where concrete classes are wired to their
interfaces.

- Trend collector  -> get_collector() (env-driven mode)
- Content generator -> TemplateContentGenerator (V1; swap later, no other
  module needs to change)
- Storage           -> LocalFirstDriveStorage (mock or live, env-driven)
- Publisher         -> GraphAPIPublisher (mock or live, env-driven)
- Scheduler         -> GenerationScheduler

Every module elsewhere in the app imports only the ABC interfaces from
app.interfaces — never a concrete class from another module.
"""
from app.config import config
from app.content_generator.generator import TemplateContentGenerator
from app.publisher.publisher import GraphAPIPublisher
from app.scheduler.scheduler import GenerationScheduler
from app.storage.drive_uploader import LocalFirstDriveStorage
from app.trend_collector.collector import get_collector


def build_application():
    """Instantiate and return all wired components."""
    collector = get_collector()
    generator = TemplateContentGenerator()
    storage = LocalFirstDriveStorage()
    publisher = GraphAPIPublisher()
    scheduler = GenerationScheduler()

    # Give the scheduler the collector/generator/storage it was built with
    # (it creates its own in __init__; here we replace them so tests or a
    # future DI container can inject fakes/mocks).
    scheduler.collector = collector
    scheduler.generator = generator
    scheduler.storage = storage

    return {
        "collector": collector,
        "generator": generator,
        "storage": storage,
        "publisher": publisher,
        "scheduler": scheduler,
        "config": config,
    }


if __name__ == "__main__":
    from app.web.server import main

    main()
