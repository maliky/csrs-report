import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { http, HttpResponse } from "msw";
import { profileFixture } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { ProfilePage } from "./ProfilePage";

test("charge et met à jour le cahier des charges", async () => {
  const user = userEvent.setup();
  let posted: {
    first_name?: string;
    last_name?: string;
    phone?: string;
    avatar?: string;
    terms_of_reference?: string;
  } | null = null;
  const updatedValues = {
    first_name: "Ariane",
    last_name: "Diallo",
    phone: "+33 06 00 00 00 00",
    avatar: "https://cdn.example.test/avatars/ariane.png",
    terms_of_reference: "Mettre à jour le plan opérationnel.",
  };

  server.use(
    http.patch("/api/v1/me/profile/", async ({ request }) => {
      posted = (await request.json()) as {
        first_name?: string;
        last_name?: string;
        phone?: string;
        avatar?: string;
        terms_of_reference?: string;
      };
      return HttpResponse.json({
        ...profileFixture,
        ...posted,
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

  const firstNameField = await screen.findByLabelText("Prénom");
  const lastNameField = screen.getByLabelText("Nom");
  const phoneField = screen.getByLabelText("Téléphone");
  const avatarField = screen.getByLabelText("Avatar");
  const torField = screen.getByLabelText("Cahier des charges");

  await waitFor(() => {
    expect(firstNameField).toHaveValue(profileFixture.first_name);
  });
  await user.clear(firstNameField);
  await user.type(firstNameField, updatedValues.first_name);
  await user.clear(lastNameField);
  await user.type(lastNameField, updatedValues.last_name);
  await user.clear(phoneField);
  await user.type(phoneField, updatedValues.phone);
  await user.clear(avatarField);
  await user.type(avatarField, updatedValues.avatar);
  await user.clear(torField);
  await user.type(torField, updatedValues.terms_of_reference);
  await user.click(screen.getByRole("button", { name: "Enregistrer" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Le profil a été mis à jour.",
  );
  expect(posted).toEqual(updatedValues);
  await waitFor(() => expect(torField).toHaveValue(updatedValues.terms_of_reference));
});
