import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { http, HttpResponse } from "msw";
import { profileFixture } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { ProfilePage } from "./ProfilePage";

test("charge et met à jour le cahier des charges", async () => {
  const user = userEvent.setup();
  let posted: { terms_of_reference?: string } | null = null;
  const updatedText = "Mettre à jour le plan opérationnel.";

  server.use(
    http.patch("/api/v1/me/profile/", async ({ request }) => {
      posted = (await request.json()) as { terms_of_reference?: string };
      return HttpResponse.json({
        ...profileFixture,
        terms_of_reference: posted.terms_of_reference ?? "",
      });
    }),
  );

  render(
    <MemoryRouter initialEntries={["/profil"]}>
      <Routes>
        <Route path="/profil" element={<ProfilePage />} />
      </Routes>
    </MemoryRouter>,
  );

  const torField = await screen.findByLabelText("Cahier des charges");
  await waitFor(() => {
    expect(torField).toHaveValue(profileFixture.terms_of_reference);
  });
  await user.clear(torField);
  await user.type(torField, updatedText);
  await user.click(screen.getByRole("button", { name: "Enregistrer" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Le cahier des charges a été mis à jour.",
  );
  expect(posted).toEqual({ terms_of_reference: updatedText });
  await waitFor(() => expect(torField).toHaveValue(updatedText));
});
