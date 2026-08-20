import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../lib/router";
import { AppShell } from "./AppShell";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { sessionFixture } from "../mocks/fixtures";

test("réduit la barre latérale et mémorise le choix", async () => {
  window.localStorage.clear();
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Contenu de test</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText("Contenu de test")).toBeInTheDocument();
  const team = screen.getByRole("link", { name: "Mon équipe" });
  const proposals = screen.getByRole("link", { name: "Propositions" });
  expect(
    screen.queryByRole("link", { name: "Interface classique" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Processus" }),
  ).not.toBeInTheDocument();
  expect(
    team.compareDocumentPosition(proposals) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Réduire le menu" }));
  expect(window.localStorage.getItem("csrs.sidebar.collapsed")).toBe("true");
  expect(
    screen.getByRole("button", { name: "Déployer le menu" }),
  ).toBeInTheDocument();
});

test("ouvre et ferme le tiroir mobile avec des contrôles accessibles", async () => {
  window.localStorage.clear();
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Contenu mobile</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByText("Contenu mobile");
  const open = screen.getByRole("button", {
    name: "Ouvrir le menu",
    hidden: true,
  });
  fireEvent.click(open);
  expect(open).toHaveAttribute("aria-expanded", "true");
  const close = screen.getByRole("button", {
    name: "Fermer le menu",
    hidden: true,
  });
  fireEvent.click(close);
  expect(open).toHaveAttribute("aria-expanded", "false");
});

test("affiche la gestion des taches uniquement avec la capacite destructive", async () => {
  server.use(
    http.get("/api/v1/session/", () =>
      HttpResponse.json({
        ...sessionFixture,
        capabilities: {
          ...sessionFixture.capabilities,
          delete_tasks: true,
        },
      }),
    ),
  );
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Administration</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  const taskManagement = await screen.findByRole("link", {
    name: "Gestion des tâches",
  });
  expect(taskManagement).toBeInTheDocument();
  expect(taskManagement.querySelector(".lucide-cog")).toBeInTheDocument();
});

test("affiche les utilisateurs et distingue l'administration avancee", async () => {
  server.use(
    http.get("/api/v1/session/", () =>
      HttpResponse.json({
        ...sessionFixture,
        capabilities: {
          ...sessionFixture.capabilities,
          manage_users: true,
          admin: true,
        },
      }),
    ),
  );
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Administration</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole("link", { name: "Utilisateurs" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Administration avancée" }),
  ).toHaveAttribute("href", "/admin/");
});

test("bloque la navigation tant que le mot de passe temporaire subsiste", async () => {
  server.use(
    http.get("/api/v1/session/", () =>
      HttpResponse.json({
        ...sessionFixture,
        capabilities: {
          ...sessionFixture.capabilities,
          password_change_required: true,
        },
      }),
    ),
  );
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Contenu protégé</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole("heading", {
      name: "Choisir un nouveau mot de passe",
    }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Contenu protégé")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Mon équipe" }),
  ).not.toBeInTheDocument();
});

test("rafraîchit l’avatar après la mise à jour du profil", async () => {
  let avatar = "";
  server.use(
    http.get("/api/v1/session/", () =>
      HttpResponse.json({
        ...sessionFixture,
        user: { ...sessionFixture.user, avatar },
      }),
    ),
  );
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Profil actualisé</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByText("Profil actualisé");
  const profileLink = screen.getByRole("link", { name: /Aïssata Koné/ });
  expect(profileLink.querySelector("img")).toBeNull();

  avatar = "https://cdn.example.test/avatar.png";
  await act(async () => {
    window.dispatchEvent(new Event("csrs:profile-updated"));
  });
  await waitFor(() =>
    expect(
      screen.getByRole("link", { name: /Aïssata Koné/ }).querySelector("img"),
    ).toHaveAttribute("src", avatar),
  );
});
