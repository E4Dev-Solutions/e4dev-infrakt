from cli.core.deployer import _generate_compose


def test_generate_compose_with_image():
    content = _generate_compose("my-api", port=8000, image="node:20")
    assert "image: node:20" in content
    assert "infrakt-my-api" in content
    assert "8000" in content


def test_generate_compose_with_build_context():
    content = _generate_compose("my-api", port=3000, build_context="./repo")
    assert "build: ./repo" in content
    assert "infrakt-my-api" in content
