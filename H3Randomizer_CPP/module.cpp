// CPP Functionality for Halo 3 Randomizer
#include <pybind11/pybind11.h>
#include <iostream>
#include <Windows.h>
#include <Tlhelp32.h>
#include <winternl.h>
#include<thread>

namespace py = pybind11;

//py::module_ H3RandomizerPy = py::module_::import("h3randomizer");

DWORD UpdateBreakpointsOnThreads(DWORD dwProcessID, DWORD64 addr1 = 0, DWORD64 addr2 = 0, DWORD64 addr3 = 0, DWORD64 addr4 = 0) // Walk all threads and set Dr0-Dr3 breakpoints as designated by respective params addr1 - addr4
{
	THREADENTRY32 te = { sizeof(THREADENTRY32) };
	HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPALL, dwProcessID);

	if (Thread32First(hSnapshot, &te))
		while (Thread32Next(hSnapshot, &te))
			if (te.th32OwnerProcessID == dwProcessID)
			{
				HANDLE hThread = OpenThread(THREAD_ALL_ACCESS, FALSE, te.th32ThreadID);

				CONTEXT ctx;
				ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
				if (GetThreadContext(hThread, &ctx))
				{
					ctx.Dr0 = addr1;
					ctx.Dr1 = addr2;
					ctx.Dr2 = addr3;
					ctx.Dr3 = addr4;
					ctx.Dr7 = 0x00000001;
					SetThreadContext(hThread, &ctx);
				}

				CloseHandle(hThread);
				hThread = NULL;
			}
	return NULL;
}

BOOL SetDebugPrivilege(BOOL State)
{
	HANDLE hToken;
	TOKEN_PRIVILEGES token_privileges;
	DWORD dwSize;

	ZeroMemory(&token_privileges, sizeof(token_privileges));
	token_privileges.PrivilegeCount = 1;

	if (!OpenProcessToken(GetCurrentProcess(), TOKEN_ALL_ACCESS, &hToken))
		return FALSE;

	if (!LookupPrivilegeValue(NULL, SE_DEBUG_NAME, &token_privileges.Privileges[0].Luid))
	{
		CloseHandle(hToken);
		return FALSE;
	}

	if (State)
		token_privileges.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
	else
		token_privileges.Privileges[0].Attributes = SE_PRIVILEGE_REMOVED;

	if (!AdjustTokenPrivileges(hToken, FALSE, &token_privileges, 0, NULL, &dwSize))
	{
		CloseHandle(hToken);
		return FALSE;
	}

	return CloseHandle(hToken);
}

// This function updates breakpoints, called from python at every loop. Maximum of 4 breakpoints per x86 register limitations.
BOOL UpdateBreakpoints(DWORD pid, DWORD64 addr1 = 0, DWORD64 addr2 = 0, DWORD64 addr3 = 0, DWORD64 addr4 = 0)
{
	SetDebugPrivilege(true);
	HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, false, pid);
	if (DebugActiveProcess(pid))
	{
		if (DebugSetProcessKillOnExit != NULL)
			DebugSetProcessKillOnExit(false);

		//std::thread thread_object([](DWORD pid, DWORD64 addr1 = 0, DWORD64 addr2 = 0, DWORD64 addr3 = 0, DWORD64 addr4 = 0) {
		//		std::cout << "Test" << std::endl;
		UpdateBreakpointsOnThreads(pid, addr1, addr2, addr3, addr4);
		//	}, pid, addr1, addr2, addr3, addr4);

		return DebugActiveProcessStop(pid);
	}
}

void HandleBreakpoints(DWORD pid, DWORD64 addr0, DWORD64 addr1 = 0x0, DWORD64 addr2 = 0x0, DWORD64 addr3 = 0x0, DWORD64 addr4 = 0x0)
{
	SetDebugPrivilege(true);
	HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, false, pid);
	if (DebugActiveProcess(pid))
	{
		if (DebugSetProcessKillOnExit != NULL)
			DebugSetProcessKillOnExit(false);
		
		DEBUG_EVENT dbgEvent;
		HANDLE hThread = NULL;
		BOOL bContinueDebugging = false;
		while (true)
		{
			WaitForDebugEvent(&dbgEvent, INFINITE);

			switch (dbgEvent.dwDebugEventCode)
			{
			case EXCEPTION_DEBUG_EVENT:
				if (dbgEvent.u.Exception.ExceptionRecord.ExceptionCode == EXCEPTION_SINGLE_STEP) // Breakpoint is triggered
				{
					if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr1
						|| dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr2
						|| dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr3
						|| dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr4) // Triggered breakpoint is one of ours
					{
						if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr1)
						{
							if (hThread = OpenThread(THREAD_ALL_ACCESS, false, dbgEvent.dwThreadId))
							{
								dbgEvent.u.Exception.ExceptionRecord.ExceptionFlags = 0;
								CONTEXT ctx;
								ctx.ContextFlags = CONTEXT_FULL;
								// stop the thread for continuing to run while we check the breakpoints
								DWORD dwSuspended = SuspendThread(&hThread);

								// get the context of the thread
								BOOL bGetThreadContext = GetThreadContext(hThread, &ctx);

								BOOL SetCxt = false;
								ctx.Rax = 4;
								ctx.EFlags |= 0x10000;
								SetCxt = true;

								// set the context so our changes are made (if needed)
								if (SetCxt) {
									BOOL bSetThreadContext = SetThreadContext(hThread, &ctx);
								}

								// resume the thread so program continues to run
								DWORD dwResumed = ResumeThread(&hThread);

								BOOL bCloseHandle = CloseHandle(hThread);

								bContinueDebugging = true;
							}
						}
						if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr2)
						{
							if (hThread = OpenThread(THREAD_ALL_ACCESS, false, dbgEvent.dwThreadId))
							{
								dbgEvent.u.Exception.ExceptionRecord.ExceptionFlags = 0;
								CONTEXT ctx;
								ctx.ContextFlags = CONTEXT_FULL;
								// stop the thread for continuing to run while we check the breakpoints
								DWORD dwSuspended = SuspendThread(&hThread);

								// get the context of the thread
								BOOL bGetThreadContext = GetThreadContext(hThread, &ctx);

								BOOL SetCxt = false;
								ctx.Rax = 4;
								ctx.EFlags |= 0x10000;
								SetCxt = true;

								// set the context so our changes are made (if needed)
								if (SetCxt) {
									BOOL bSetThreadContext = SetThreadContext(hThread, &ctx);
								}

								// resume the thread so program continues to run
								DWORD dwResumed = ResumeThread(&hThread);

								BOOL bCloseHandle = CloseHandle(hThread);

								bContinueDebugging = true;
							}
						}
						if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr3)
						{
							if (hThread = OpenThread(THREAD_ALL_ACCESS, false, dbgEvent.dwThreadId))
							{
								dbgEvent.u.Exception.ExceptionRecord.ExceptionFlags = 0;
								CONTEXT ctx;
								ctx.ContextFlags = CONTEXT_FULL;
								// stop the thread for continuing to run while we check the breakpoints
								DWORD dwSuspended = SuspendThread(&hThread);

								// get the context of the thread
								BOOL bGetThreadContext = GetThreadContext(hThread, &ctx);

								BOOL SetCxt = false;
								ctx.Rax = 4;
								ctx.EFlags |= 0x10000;
								SetCxt = true;

								// set the context so our changes are made (if needed)
								if (SetCxt) {
									BOOL bSetThreadContext = SetThreadContext(hThread, &ctx);
								}

								// resume the thread so program continues to run
								DWORD dwResumed = ResumeThread(&hThread);

								BOOL bCloseHandle = CloseHandle(hThread);

								bContinueDebugging = true;
							}
						}
						if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr4)
						{
							if (hThread = OpenThread(THREAD_ALL_ACCESS, false, dbgEvent.dwThreadId))
							{
								dbgEvent.u.Exception.ExceptionRecord.ExceptionFlags = 0;
								CONTEXT ctx;
								ctx.ContextFlags = CONTEXT_FULL;
								// stop the thread for continuing to run while we check the breakpoints
								DWORD dwSuspended = SuspendThread(&hThread);

								// get the context of the thread
								BOOL bGetThreadContext = GetThreadContext(hThread, &ctx);

								BOOL SetCxt = false;
								ctx.Rax = 4;
								ctx.EFlags |= 0x10000;
								SetCxt = true;

								// set the context so our changes are made (if needed)
								if (SetCxt) {
									BOOL bSetThreadContext = SetThreadContext(hThread, &ctx);
								}

								// resume the thread so program continues to run
								DWORD dwResumed = ResumeThread(&hThread);

								BOOL bCloseHandle = CloseHandle(hThread);

								bContinueDebugging = true;
							}
						}
					}
				}
				if (bContinueDebugging)
				{
					BOOL bContinue = ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_CONTINUE);
					bContinueDebugging = false;
				}
				else
					ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_EXCEPTION_NOT_HANDLED);

				break;
			default:
				ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_EXCEPTION_NOT_HANDLED);
				break;
			}
		}
		std::cout << "H3Randomizer_CPP Done" << std::endl;
		return;
	}

}

/*void CreateBreakpoint(DWORD pid, DWORD64 addr)
{
	SetDebugPrivilege(true);
	HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, false, pid);
	if (DebugActiveProcess(pid))
	{
		if (DebugSetProcessKillOnExit != NULL)
			DebugSetProcessKillOnExit(false);

		std::thread thread_object([](DWORD pid, DWORD64 addr) {
			while (true) {
				SetBreakpointOnThreads(pid, addr);
			}
			}, pid, addr); // Create new thread to set breakpoints on threads.

		DEBUG_EVENT dbgEvent;
		BOOL bContinueDebugging = false;
		while (true)
		{
			WaitForDebugEvent(&dbgEvent, INFINITE);

			switch (dbgEvent.dwDebugEventCode)
			{
			case EXCEPTION_DEBUG_EVENT:
				if (dbgEvent.u.Exception.ExceptionRecord.ExceptionCode == EXCEPTION_SINGLE_STEP) // Breakpoint is triggered
				{
					if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)addr) // Triggered breakpoint is one of ours
					{
						if (hThread = OpenThread(THREAD_ALL_ACCESS, false, dbgEvent.dwThreadId))
						{
							dbgEvent.u.Exception.ExceptionRecord.ExceptionFlags = 0;
							CONTEXT ctx;
							ctx.ContextFlags = CONTEXT_FULL;
							// stop the thread for continuing to run while we check the breakpoints
							DWORD dwSuspended = SuspendThread(&hThread);

							// get the context of the thread
							BOOL bGetThreadContext = GetThreadContext(hThread, &ctx);

							BOOL SetCxt = false;
							ctx.Rax = 4;
							ctx.EFlags |= 0x10000;
							SetCxt = true;

							// set the context so our changes are made (if needed)
							if (SetCxt) {
								BOOL bSetThreadContext = SetThreadContext(hThread, &ctx);
							}

							// resume the thread so program continues to run
							DWORD dwResumed = ResumeThread(&hThread);

							BOOL bCloseHandle = CloseHandle(hThread);

							BOOL bContinue = ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_CONTINUE);

							break;
						}
					}
					else {
						// if the exception was not handled by our exception-handler, we want the program to handle it, so..
						ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_EXCEPTION_NOT_HANDLED);
						break;
					}
				}
				else {
					ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_EXCEPTION_NOT_HANDLED);
					break;
				}
				break;
			default:
				ContinueDebugEvent(dbgEvent.dwProcessId, dbgEvent.dwThreadId, DBG_EXCEPTION_NOT_HANDLED);
				break;
			}
		}
	}
}*/


PYBIND11_MODULE(H3Randomizer_CPP, m)
{
	/*m.def("fn_name_py", &fn_name_cpp, R"pbdoc(
		Docstring
	)pbdoc");*/
	m.def("update_breakpoints", &UpdateBreakpoints, R"pbdoc(
        Sets, removes, or updates breakpoints to the register corresponding to addr1 (Dr0) through addr4 (Dr3).
    )pbdoc");
	m.def("handle_breakpoints", &HandleBreakpoints, R"pbdoc(
        Handles breakpoint debug events.
    )pbdoc");

#ifdef VERSION_INFO
	m.attr("__version__") = VERSION_INFO;
#else
	m.attr("__version__") = "dev";
#endif
}