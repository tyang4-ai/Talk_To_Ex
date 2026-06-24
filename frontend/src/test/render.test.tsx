import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Landing from "../pages/Landing";
import GradientButton from "../components/GradientButton";
import ChatBubble from "../components/ChatBubble";
import StepGuide from "../components/StepGuide";
import { microcopy } from "../lib/theme";

describe("Landing", () => {
  it("renders the locked tagline microcopy", () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );
    expect(screen.getByText(microcopy.tagline)).toBeInTheDocument();
  });
});

describe("GradientButton", () => {
  it("fires onClick and shows children", () => {
    const onClick = vi.fn();
    render(<GradientButton onClick={onClick}>Tap me</GradientButton>);
    const btn = screen.getByRole("button", { name: /tap me/i });
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("is disabled while loading", () => {
    render(<GradientButton loading>Go</GradientButton>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});

describe("ChatBubble", () => {
  it("renders mixed zh/en text", () => {
    render(<ChatBubble text="在吗 you up?" side="out" />);
    expect(screen.getByText("在吗 you up?")).toBeInTheDocument();
  });
});

describe("StepGuide", () => {
  it("numbers the steps in order", () => {
    render(
      <StepGuide
        platform="WhatsApp"
        emoji="💬"
        steps={[{ title: "Open the chat" }, { title: "Export chat" }]}
      />,
    );
    expect(screen.getByText("Open the chat")).toBeInTheDocument();
    expect(screen.getByText("Export chat")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
