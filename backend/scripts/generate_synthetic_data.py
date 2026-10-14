"""Generate the deterministic ShopQuery CSV dataset."""

from app.core.config import get_settings
from app.database.seed_data import calculate_completed_revenue, generate_seed_data, write_seed_csv


def main() -> None:
    settings = get_settings()
    data = generate_seed_data()
    write_seed_csv(data, settings.seed_directory)
    print(
        f"Generated 8 categories, 150 products, 2000 orders, "
        f"{len(data.order_items)} order items. "
        f"Completed revenue: {calculate_completed_revenue(data):,.0f} VND"
    )


if __name__ == "__main__":
    main()
