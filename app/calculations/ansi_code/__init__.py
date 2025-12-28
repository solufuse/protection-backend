
from . import ansi_51
from . import ansi_67

# You can register available functions here for dynamic lookup
AVAILABLE_ANSI_MODULES = {
    "51": ansi_51,
    "67": ansi_67
}
