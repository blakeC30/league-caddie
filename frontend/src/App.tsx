/**
 * App — root router.
 *
 * Public routes (/login, /register, /join/:inviteCode) are accessible without auth.
 * All other routes are wrapped in <Layout>, which redirects to /login if there
 * is no token.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "./components/Toaster";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Welcome } from "./pages/Welcome";
import { Leagues } from "./pages/Leagues";
import { Dashboard } from "./pages/Dashboard";
import { MakePick } from "./pages/MakePick";
import { MyPicks } from "./pages/MyPicks";
import { Leaderboard } from "./pages/Leaderboard";
import { ManageLeague } from "./pages/ManageLeague";
import { PlatformAdmin } from "./pages/PlatformAdmin";
import { JoinLeague } from "./pages/JoinLeague";
import { Settings } from "./pages/Settings";
import { CreateLeague } from "./pages/CreateLeague";
import { TournamentDetail } from "./pages/TournamentDetail";
import { PlayoffBracket } from "./pages/PlayoffBracket";
import { PlayoffDraft } from "./pages/PlayoffDraft";
import { ForgotPassword } from "./pages/ForgotPassword";
import { ResetPassword } from "./pages/ResetPassword";
import { LeagueRules } from "./pages/LeagueRules";
import { Pricing } from "./pages/Pricing";
import { BillingSuccess } from "./pages/BillingSuccess";
import { BillingCanceled } from "./pages/BillingCanceled";

export default function App() {
  return (
    <>
    <Routes>
      {/* Public */}
      <Route path="/" element={<Welcome />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/join/:inviteCode" element={<JoinLeague />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/billing/success" element={<BillingSuccess />} />
      <Route path="/billing/canceled" element={<BillingCanceled />} />

      {/* Auth-guarded — all share the Layout shell */}
      <Route element={<Layout />}>
        <Route path="/leagues" element={<Leagues />} />
        <Route path="/leagues/new" element={<CreateLeague />} />
        <Route path="/leagues/:leagueId" element={<Dashboard />} />
        <Route path="/leagues/:leagueId/pick" element={<MakePick />} />
        <Route path="/leagues/:leagueId/picks" element={<MyPicks />} />
        <Route path="/leagues/:leagueId/tournaments/:tournamentId" element={<TournamentDetail />} />
        <Route path="/leagues/:leagueId/leaderboard" element={<Leaderboard />} />
        <Route path="/leagues/:leagueId/manage" element={<ManageLeague />} />
        <Route path="/leagues/:leagueId/playoff" element={<PlayoffBracket />} />
        <Route path="/leagues/:leagueId/playoff/pod/:podId" element={<PlayoffDraft />} />
        <Route path="/leagues/:leagueId/rules" element={<LeagueRules />} />
        <Route path="/admin" element={<PlatformAdmin />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      {/* Unknown routes: send to welcome */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    <Toaster />
    </>
  );
}
