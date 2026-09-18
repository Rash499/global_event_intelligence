const formatOption = (value) =>
  value === "all" ? "All categories" : value.replaceAll("_", " ");

export default function GlobalDashboardFilters({
  category,
  onCategoryChange,
  categories,
  country,
  onCountryChange,
  countries,
  minImportance,
  onImportanceChange,
  hasActiveFilters,
  onReset,
}) {
  return (
    <div className="advanced-filters">
      <div className="filters-heading">
        <span className="section-eyebrow">Refine intelligence</span>
        {hasActiveFilters && (
          <button className="reset-filters" type="button" onClick={onReset}>
            Reset filters <span aria-hidden="true">↺</span>
          </button>
        )}
      </div>

      <div>
        <label htmlFor="dashboard-category">Category</label>
        <select
          id="dashboard-category"
          value={category}
          onChange={(event) => onCategoryChange(event.target.value)}
        >
          {categories.map((item) => (
            <option key={item} value={item}>
              {formatOption(item)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="dashboard-country">Country</label>
        <select
          id="dashboard-country"
          value={country}
          onChange={(event) => onCountryChange(event.target.value)}
        >
          {countries.map((item) => (
            <option key={item} value={item}>
              {item === "all" ? "All countries" : item}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="dashboard-importance">
          Minimum importance: {minImportance}
        </label>
        <input
          id="dashboard-importance"
          type="range"
          min="1"
          max="10"
          value={minImportance}
          onChange={(event) => onImportanceChange(Number(event.target.value))}
        />
      </div>
    </div>
  );
}
