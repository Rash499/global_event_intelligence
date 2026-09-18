import { categories } from "../types.jsx";

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