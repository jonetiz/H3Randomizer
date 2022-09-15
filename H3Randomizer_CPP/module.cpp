// CPP Functionality for Halo 3 Randomizer
#include <pybind11/pybind11.h>
#include <iostream>
#include <Windows.h>
#include <Tlhelp32.h>
#include <winternl.h>
#include <thread>

namespace py = pybind11;

DWORD UpdateBreakpointsOnThreads(DWORD dwProcessID, DWORD64 addr, int index) // Walk all threads and set Dr0-Dr3 breakpoints as designated by respective params addr1 - addr4
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
					// DWORD64 dFinalDr7[4];
					if (index == 0) {
						ctx.Dr0 = addr;
					}
					if (index == 1) {
						ctx.Dr1 = addr;
					}
					if (index == 2) {
						ctx.Dr2 = addr;
					}
					if (index == 3) {
						ctx.Dr3 = addr;
					}

					ctx.Dr7 = (1 << 0) | (1 << 2) | (1 << 4) | (1 << 6);

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

class PythonContext { // Class used to hold a CONTEXT object and convert to/from python dictionary
public:
	CONTEXT ctxOriginal;
	py::dict ctxPython;
	PythonContext(CONTEXT ctx) {
		ctxOriginal = ctx; // Only worrying about GPRs
		//x86 GPRs
		ctxPython["Rax"] = ctx.Rax;
		ctxPython["Rcx"] = ctx.Rcx;
		ctxPython["Rdx"] = ctx.Rdx;
		ctxPython["Rbx"] = ctx.Rbx;
		ctxPython["Rsp"] = ctx.Rsp;
		ctxPython["Rbp"] = ctx.Rbp;
		ctxPython["Rsi"] = ctx.Rsi;
		ctxPython["Rdi"] = ctx.Rdi;
		//x86_64 GPRs
		ctxPython["R8"] = ctx.R8;
		ctxPython["R9"] = ctx.R9;
		ctxPython["R10"] = ctx.R10;
		ctxPython["R11"] = ctx.R11;
		ctxPython["R12"] = ctx.R12;
		ctxPython["R13"] = ctx.R13;
		ctxPython["R14"] = ctx.R14;
		ctxPython["R15"] = ctx.R15;
	}
	CONTEXT ConvertFromPython(py::dict ctxPy) {
		CONTEXT ctxOut = ctxOriginal; // Set ctxOut to same values as ctxOriginal

		ctxOut.Rax = ctxPy["Rax"].cast<uint64_t>();
		ctxOut.Rcx = ctxPy["Rcx"].cast<uint64_t>();
		ctxOut.Rdx = ctxPy["Rdx"].cast<uint64_t>();
		ctxOut.Rbx = ctxPy["Rbx"].cast<uint64_t>();
		ctxOut.Rsp = ctxPy["Rsp"].cast<uint64_t>();
		ctxOut.Rbp = ctxPy["Rbp"].cast<uint64_t>();
		ctxOut.Rsi = ctxPy["Rsi"].cast<uint64_t>();
		ctxOut.Rdi = ctxPy["Rdi"].cast<uint64_t>();
		ctxOut.R8 = ctxPy["R8"].cast<uint64_t>();
		ctxOut.R9 = ctxPy["R9"].cast<uint64_t>();
		ctxOut.R10 = ctxPy["R10"].cast<uint64_t>();
		ctxOut.R11 = ctxPy["R11"].cast<uint64_t>();
		ctxOut.R12 = ctxPy["R12"].cast<uint64_t>();
		ctxOut.R13 = ctxPy["R13"].cast<uint64_t>();
		ctxOut.R14 = ctxPy["R14"].cast<uint64_t>();
		ctxOut.R15 = ctxPy["R15"].cast<uint64_t>();

		return ctxOut;
	}
};

class Breakpoint
{
public:
	DWORD64 address;
	py::function callback;
	Breakpoint() {
		address = 0x0;
		callback = py::function();
	}
	Breakpoint(DWORD64 addr, py::function cb) {
		address = addr; // Breakpoint address
		callback = cb; // What to do when hit
	}
	CONTEXT CallbackWithContext(CONTEXT ctx) { // Run callback() passing context of breakpoint as arg and return the altered context
		PythonContext converter = PythonContext(ctx);
		py::dict ctxPassed = converter.ctxPython;
		py::dict cb = callback(ctxPassed);
		CONTEXT ctxRecieved = converter.ConvertFromPython(cb);
		return ctxRecieved;
	}
};

class H3Randomizer
{
	public:
		DWORD pid;
		Breakpoint breakpoints[4]; // Storing Breakpoint objects to be iterated over
		bool bHandleBreakpoints = false; // Used to halt while loop 

		H3Randomizer(DWORD p)
		{
			pid = p;
		}
		
		void SetBreakpoint(int i, Breakpoint b) {
			H3Randomizer::breakpoints[i] = b;
		}

		void StartHandlingBreakpoints() {
			py::gil_scoped_release release;
			bHandleBreakpoints = true;
			UpdateBreakpoints(); // Update breakpoints on target process
			HandleBreakpoints();
			py::gil_scoped_acquire acquire;
		}

		void UpdateBreakpoints() {
			SetDebugPrivilege(true);
			HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, false, H3Randomizer::pid);
			if (DebugActiveProcess(H3Randomizer::pid))
			{
				if (DebugSetProcessKillOnExit != NULL)
					DebugSetProcessKillOnExit(false);

				int counter = 0; // Keep track of array index and debug register
				for (Breakpoint & breakpoint : H3Randomizer::breakpoints) {
					if (breakpoint.address != 0x0) {
						UpdateBreakpointsOnThreads(H3Randomizer::pid, breakpoint.address, counter);
					}
					counter += 1;
				}

				DebugActiveProcessStop(H3Randomizer::pid);
			}
		}
		void HandleBreakpoints() {
			SetDebugPrivilege(true);
			HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, false, H3Randomizer::pid);
			if (DebugActiveProcess(H3Randomizer::pid))
			{
				if (DebugSetProcessKillOnExit != NULL)
					DebugSetProcessKillOnExit(false);
				
				DEBUG_EVENT dbgEvent;
				HANDLE hThread = NULL;
				BOOL bContinueDebugging = false;
				while (H3Randomizer::bHandleBreakpoints)
				{
					WaitForDebugEvent(&dbgEvent, INFINITE);

					switch (dbgEvent.dwDebugEventCode)
					{
					case EXCEPTION_DEBUG_EVENT:
						if (dbgEvent.u.Exception.ExceptionRecord.ExceptionCode == EXCEPTION_SINGLE_STEP) // Breakpoint is triggered
						{
							for (Breakpoint breakpoint : H3Randomizer::breakpoints) { // Foreach breakpoint in array check if this is the one
								if (dbgEvent.u.Exception.ExceptionRecord.ExceptionAddress == (void*)breakpoint.address)
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

										py::gil_scoped_acquire acquire;
										CONTEXT callback = breakpoint.CallbackWithContext(ctx);
										py::gil_scoped_release release;

										ctx = callback;

										ctx.EFlags |= 0x10000;

										// set the context so our changes are made
										BOOL bSetThreadContext = SetThreadContext(hThread, &ctx);

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
			}
			DebugActiveProcessStop(H3Randomizer::pid);
			CloseHandle(hProcess);
		}

		void Stop() {
			//Set HandleBreakpoints to false so while loop terminates
			H3Randomizer::bHandleBreakpoints = false;

			// Remove breakpoints
			H3Randomizer::breakpoints[0] = Breakpoint();
			H3Randomizer::breakpoints[1] = Breakpoint();
			H3Randomizer::breakpoints[2] = Breakpoint();
			H3Randomizer::breakpoints[3] = Breakpoint();
			UpdateBreakpoints();
		}
};

H3Randomizer CurrentRandomizer = H3Randomizer(NULL); // The currently instantiated randomizer object

void CreateRandomizer(DWORD pid) {
	CurrentRandomizer = H3Randomizer(pid);
}

H3Randomizer* AccessRandomizer() {
	return &CurrentRandomizer;
}


// This function updates breakpoints, called from python at every loop. Maximum of 4 breakpoints per x86 register limitations.
/*void UpdateBreakpoints(DWORD pid, DWORD64 addr1 = 0, DWORD64 addr2 = 0, DWORD64 addr3 = 0, DWORD64 addr4 = 0)
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

		DebugActiveProcessStop(pid);
	}
}

void HandleBreakpoints(DWORD pid, DWORD64 addr1 = 0, DWORD64 addr2 = 0, DWORD64 addr3 = 0, DWORD64 addr4 = 0)
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
	}

}*/

PYBIND11_MODULE(H3Randomizer_CPP, m)
{
	/*m.def("fn_name_py", &fn_name_cpp, R"pbdoc(
		Docstring
	)pbdoc");*/
	//m.def("update_breakpoints", &UpdateBreakpoints, R"pbdoc(
    //    Sets, removes, or updates breakpoints to the register corresponding to addr1 (Dr0) through addr4 (Dr3).
    //)pbdoc");
	m.def("create_randomizer", &CreateRandomizer, R"pbdoc(
        Instantiates a H3Randomizer object and places into CurrentRandomizer.
    )pbdoc");
	m.def("access_randomizer", &AccessRandomizer, R"pbdoc(
        Accesses the H3Randomizer object currently in CurrentRandomizer.
    )pbdoc");

	py::class_<Breakpoint>(m, "Breakpoint")
		.def(py::init<DWORD64 &, py::function &>());
	py::class_<H3Randomizer>(m, "h3randomizer_obj_cpp")
		.def(py::init<DWORD&>())
		.def("set_breakpoint", &H3Randomizer::SetBreakpoint)
		.def("start_handling_breakpoints", &H3Randomizer::StartHandlingBreakpoints)
		.def("stop", &H3Randomizer::Stop)
		.def_readwrite("handle_breakpoints", &H3Randomizer::bHandleBreakpoints)
		.def_readonly("pid", &H3Randomizer::pid);

#ifdef VERSION_INFO
	m.attr("__version__") = VERSION_INFO;
#else
	m.attr("__version__") = "DEV";
#endif
}
