import { categories } from "../types.jsx";

export default function CategoryFilter({
  selectedCategory,
  onChange,
}) {
  return (
    <section className="filters" aria-label="Filter events by category">
      <div className="filter-heading">
        <span className="section-eyebrow">Signal type</span>
        <span className="filter-selection">
          {selectedCategory === "all"
            ? "All signals"
            : selectedCategory.replaceAll("_", " ")}
        </span>
      </div>

      <div className="filter-options">
        {categories.map((category) => (
        <button
          key={category}
          type="button"
          aria-pressed={selectedCategory === category}
          className={
            selectedCategory === category
              ? "filter-button active"
              : "filter-button"
          }
          onClick={() => onChange(category)}
        >
          {category === "all" ? "All signals" : category.replaceAll("_", " ")}
        </button>
        ))}
      </div>
    </section>
  );
}