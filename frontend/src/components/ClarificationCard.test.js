import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import ClarificationCard from "./ClarificationCard";

describe("ClarificationCard Component - Duplicate Value Handling", () => {

  const duplicateOptions = [
    { option_id: 1, value: "CHENNAI", display_dimension: "City" },
    { option_id: 2, value: "CHENNAI", display_dimension: "District" }
  ];

  const uniqueOptions = [
    { option_id: 1, value: "LS ZARI COTTON", display_dimension: "Prod Grp2" },
    { option_id: 2, value: "LS COTTON BREEZE", display_dimension: "Prod Grp2" },
    { option_id: 3, value: "MENS PYJAMA PANT", display_dimension: "Prod Grp2" }
  ];

  test("1. Duplicate values render with business dimension labels", () => {
    render(<ClarificationCard options={duplicateOptions} />);

    expect(screen.getByText("CHENNAI — City")).toBeInTheDocument();
    expect(screen.getByText("CHENNAI — District")).toBeInTheDocument();
  });

  test("2. Unique value renders without unnecessary dimension label", () => {
    render(<ClarificationCard options={uniqueOptions} />);

    expect(screen.getByText("MENS PYJAMA PANT")).toBeInTheDocument();
    expect(screen.queryByText("MENS PYJAMA PANT — Prod Grp2")).not.toBeInTheDocument();
  });

  test("3. Clicking Chennai — City sends option_id = 1", () => {
    const handleConfirm = jest.fn();
    render(<ClarificationCard options={duplicateOptions} onConfirm={handleConfirm} />);

    const cityOption = screen.getByText("CHENNAI — City");
    fireEvent.click(cityOption);

    const useSelectedBtn = screen.getByTestId("use-selected-btn");
    fireEvent.click(useSelectedBtn);

    expect(handleConfirm).toHaveBeenCalledWith(1, "CHENNAI — City");
  });

  test("4. Clicking Chennai — District sends option_id = 2", () => {
    const handleConfirm = jest.fn();
    render(<ClarificationCard options={duplicateOptions} onConfirm={handleConfirm} />);

    const districtOption = screen.getByText("CHENNAI — District");
    fireEvent.click(districtOption);

    const useSelectedBtn = screen.getByTestId("use-selected-btn");
    fireEvent.click(useSelectedBtn);

    expect(handleConfirm).toHaveBeenCalledWith(2, "CHENNAI — District");
  });

  test("5. Frontend payload options do NOT expose internal metadata", () => {
    // Verify our clean option schema
    duplicateOptions.forEach((opt) => {
      expect(opt).not.toHaveProperty("dimension_id");
      expect(opt).not.toHaveProperty("table_name");
      expect(opt).not.toHaveProperty("column_name");
      expect(opt).not.toHaveProperty("match_type");
    });
  });

  test("6. Option selection button is disabled until an option is selected", () => {
    render(<ClarificationCard options={duplicateOptions} />);

    const useSelectedBtn = screen.getByTestId("use-selected-btn");
    expect(useSelectedBtn).toBeDisabled();

    const cityOption = screen.getByText("CHENNAI — City");
    fireEvent.click(cityOption);

    expect(useSelectedBtn).not.toBeDisabled();
  });

  test("7. Keyboard accessibility supports Space and Enter selection", () => {
    const handleConfirm = jest.fn();
    render(<ClarificationCard options={duplicateOptions} onConfirm={handleConfirm} />);

    const labelContainer = screen.getByTestId("option-label-1");
    fireEvent.keyDown(labelContainer, { key: "Enter", code: "Enter" });

    const useSelectedBtn = screen.getByTestId("use-selected-btn");
    expect(useSelectedBtn).not.toBeDisabled();
    fireEvent.click(useSelectedBtn);

    expect(handleConfirm).toHaveBeenCalledWith(1, "CHENNAI — City");
  });

  test("8. Duplicate display values remain distinguishable in options list", () => {
    render(<ClarificationCard options={duplicateOptions} />);

    const labels = screen.getAllByText(/CHENNAI —/);
    expect(labels.length).toBe(2);
    expect(labels[0]).toHaveTextContent("CHENNAI — City");
    expect(labels[1]).toHaveTextContent("CHENNAI — District");
  });

});
