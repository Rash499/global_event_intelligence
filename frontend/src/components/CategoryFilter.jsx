import { categories } from "../types";

export default function CategoryFilter({
  selectedCategory,
  onChange,
}) {
  return (
    <section className="filters">
      {categories.map((category) => (
        <button
          key={category}
          className={
            selectedCategory === category
              ? "filter-button active"
              : "filter-button"
          }
          onClick={() => onChange(category)}
        >
          {category.replace("_", " ")}
        </button>
      ))}
    </section>
  );
}