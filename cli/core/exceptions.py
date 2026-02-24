class InfraktError(Exception):
    """Base exception for all infrakt errors."""


class SSHConnectionError(InfraktError):
    """Failed to connect or execute command over SSH."""


class ProvisioningError(InfraktError):
    """Server provisioning failed."""


class DeploymentError(InfraktError):
    """App deployment failed."""


class AppNotFoundError(InfraktError):
    """Requested app does not exist."""


class ServerNotFoundError(InfraktError):
    """Requested server does not exist."""
